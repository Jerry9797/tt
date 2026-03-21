import json
import logging
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from pydantic import BaseModel, Field

# 将项目根目录添加到 sys.path，支持直接用 `python src/fastapi/app.py` 启动。
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.graph_state import AgentState
from src.nodes.build_graph import build_graph

app = FastAPI(
    title="TT Assistant API",
    description="TT Assistant API",
    version="v0.1",
)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    query: Optional[str] = None
    thread_id: Optional[str] = None
    resume_input: Optional[str] = None
    history: Optional[List[dict]] = Field(default_factory=list)


class StepResultResponse(BaseModel):
    step_index: int
    description: str
    status: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[float] = None
    output: Optional[str] = None
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    token_usage: Optional[Dict[str, int]] = None


class ChatResponse(BaseModel):
    query: Optional[str] = None
    intent: Optional[str] = None
    faq_response: Optional[str] = None
    plan: Optional[List[str]] = None
    response: Optional[str] = None
    thread_id: Optional[str] = None
    status: str = "success"
    step_results: Optional[List[StepResultResponse]] = None
    execution_summary: Optional[Dict[str, Any]] = None


class StreamMessageResponse(BaseModel):
    id: Optional[str] = None
    type: str
    content: str = ""


class StreamEventResponse(BaseModel):
    thread_id: str
    mode: str
    data: Dict[str, Any] = Field(default_factory=dict)


def build_initial_state(request: ChatRequest) -> AgentState:
    # 这里构造的是“最小可运行状态”：
    # 只放图入口一定会用到的字段，其余字段交给节点按需补齐。
    initial_state = AgentState()
    initial_state["original_query"] = request.query or ""
    initial_state["plan"] = []
    initial_state["current_step"] = 0

    messages = []
    for msg in request.history or []:
        if msg.get("role") == "user":
            messages.append(HumanMessage(content=msg.get("content")))
        elif msg.get("role") == "assistant":
            messages.append(AIMessage(content=msg.get("content")))
    initial_state["messages"] = messages
    return initial_state


def resolve_thread_id(thread_id: Optional[str]) -> str:
    return thread_id or f"thread_{uuid4().hex}"


def serialize_step_results(step_results: Optional[List[Any]]) -> Optional[List[StepResultResponse]]:
    if not step_results:
        return None

    return [
        StepResultResponse(
            step_index=result.step_index,
            description=result.step_description,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            start_time=result.start_time.isoformat() if result.start_time else None,
            end_time=result.end_time.isoformat() if result.end_time else None,
            duration_ms=result.duration_ms,
            output=result.output_result,
            error=result.error_message,
            tool_calls=[tool_call.model_dump() for tool_call in getattr(result, "tool_calls", [])],
            token_usage=result.token_usage.dict() if result.token_usage else None,
        )
        for result in step_results
    ]


def serialize_execution_summary(summary: Any) -> Optional[Dict[str, Any]]:
    if not summary:
        return None

    return {
        "plan_id": getattr(summary, "plan_id", None),
        "query": summary.query,
        "intent": summary.intent,
        "is_sop": summary.is_sop,
        "total_steps": summary.total_steps,
        "completed_steps": summary.completed_steps,
        "failed_steps": summary.failed_steps,
        "overall_status": summary.overall_status.value if hasattr(summary.overall_status, "value") else str(summary.overall_status),
        "total_duration_ms": summary.total_duration_ms,
        "start_time": summary.start_time.isoformat() if summary.start_time else None,
        "end_time": summary.end_time.isoformat() if summary.end_time else None,
        "token_usage": summary.total_token_usage.dict() if summary.total_token_usage else None,
    }


def build_chat_response(result: Dict[str, Any], request: ChatRequest, thread_id: str, status: str = "success") -> ChatResponse:
    # 对外 API 继续保留 `response` 字段，但内部状态已经拆成：
    # - `final_response`：真正的最终答案
    # - `clarification_question`：需要用户补充时的问题
    # 这里负责做兼容映射，避免前端/UI 需要跟着内部重构一起改。
    response_text = result.get("final_response") or result.get("response")
    if status == "need_clarification":
        response_text = result.get("clarification_question") or result.get("response")

    return ChatResponse(
        query=result.get("original_query", request.query),
        intent=result.get("intent"),
        faq_response=result.get("faq_response"),
        plan=result.get("plan"),
        response=response_text,
        thread_id=result.get("thread_id", thread_id),
        status=status,
        step_results=serialize_step_results(result.get("step_results")),
        execution_summary=serialize_execution_summary(result.get("execution_summary")),
    )


def extract_interrupt_question(state_snapshot: Any) -> Optional[str]:
    tasks = list(state_snapshot.tasks)
    if not tasks or not tasks[0].interrupts:
        return None

    interrupt_value = tasks[0].interrupts[0].value
    if isinstance(interrupt_value, str):
        return interrupt_value
    if isinstance(interrupt_value, dict):
        return interrupt_value.get("question", str(interrupt_value))
    return str(interrupt_value)


def build_graph_input(request: ChatRequest) -> AgentState | Command:
    if request.resume_input:
        logger.info("Resuming interrupted graph execution")
        # LangGraph 的 resume 机制会把这段字符串送回上次 interrupt 的位置，
        # 再由 ask_human 节点写入 `resume_input`，交给目标节点消费。
        return Command(resume=request.resume_input)

    return build_initial_state(request)


async def execute_chat_request(request: ChatRequest) -> tuple[Dict[str, Any], str, str]:
    graph = None
    thread_id = resolve_thread_id(request.thread_id)
    try:
        graph = await build_graph(init_mcp=False)
        config = {"configurable": {"thread_id": thread_id}}
        result = {}

        try:
            result = await graph.ainvoke(build_graph_input(request), config=config)
        except GraphInterrupt:
            logger.info("Graph execution interrupted for thread_id=%s", thread_id)

        state_snapshot = await graph.aget_state(config)
        question = extract_interrupt_question(state_snapshot)
        if question:
            return (
                {
                    # 内部状态已经不再复用 `response` 表示澄清问题；
                    # 这里先返回语义化字段，再由 build_chat_response 做 API 兼容映射。
                    "clarification_question": question,
                    "thread_id": thread_id,
                },
                "need_clarification",
                thread_id,
            )

        if result is None:
            result = state_snapshot.values or {}

        result["thread_id"] = thread_id
        return result, "success", thread_id
    finally:
        await cleanup_runtime(graph)


async def cleanup_runtime(graph: Any) -> None:
    try:
        from src.mcp.mcp_manager import cleanup_mcp_manager

        await cleanup_mcp_manager()
    except Exception as exc:
        logger.warning("Error cleaning MCP manager: %s", exc)

    if graph and hasattr(graph.checkpointer, "conn"):
        try:
            graph.checkpointer.conn.close()
        except Exception as exc:
            logger.warning("Error closing DB connection: %s", exc)


def encode_sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def normalize_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content) if content is not None else ""


def make_json_safe(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        return StreamMessageResponse(
            id=value.id,
            type=value.type,
            content=normalize_message_content(value.content),
        ).model_dump()
    if isinstance(value, BaseModel):
        return make_json_safe(value.model_dump())
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def build_updates_event_payload(thread_id: str, update: Dict[str, Any]) -> StreamEventResponse:
    node_name, payload = next(iter(update.items()))
    return StreamEventResponse(
        thread_id=thread_id,
        mode="updates",
        data={
            "node": node_name,
            "payload": make_json_safe(payload),
        },
    )


def build_messages_event_payload(
    thread_id: str,
    message: BaseMessage,
    metadata: Dict[str, Any],
) -> StreamEventResponse:
    return StreamEventResponse(
        thread_id=thread_id,
        mode="messages",
        data={
            "message": make_json_safe(message),
            "metadata": make_json_safe(metadata),
        },
    )


async def emit_graph_stream(
    graph: Any,
    graph_input: AgentState | Command,
    config: Dict[str, Any],
) -> AsyncIterator[str]:
    async for update in graph.astream(
        graph_input,
        config=config,
        stream_mode=["updates", "messages"],
    ):
        if not isinstance(update, tuple) or len(update) != 2:
            continue

        mode, chunk = update
        thread_id = config["configurable"]["thread_id"]

        if mode == "updates" and isinstance(chunk, dict) and chunk:
            yield encode_sse(
                "updates",
                build_updates_event_payload(thread_id, chunk).model_dump(),
            )
        elif mode == "messages" and isinstance(chunk, tuple) and len(chunk) == 2:
            message, metadata = chunk
            if isinstance(message, BaseMessage) and isinstance(metadata, dict):
                yield encode_sse(
                    "messages",
                    build_messages_event_payload(thread_id, message, metadata).model_dump(),
                )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        result, status, thread_id = await execute_chat_request(request)
        return build_chat_response(
            result=result,
            request=request,
            thread_id=thread_id,
            status=status,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Chat request failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def event_generator() -> AsyncIterator[str]:
        graph = None
        thread_id = resolve_thread_id(request.thread_id)
        config = {"configurable": {"thread_id": thread_id}}

        try:
            graph = await build_graph(init_mcp=False)
            yield encode_sse(
                "metadata",
                {
                    "thread_id": thread_id,
                    "mode": "metadata",
                    "data": {"message": "started"},
                },
            )

            try:
                async for event in emit_graph_stream(graph, build_graph_input(request), config):
                    yield event
            except GraphInterrupt:
                logger.info("Graph stream interrupted for thread_id=%s", thread_id)

            state_snapshot = await graph.aget_state(config)
            question = extract_interrupt_question(state_snapshot)
            if question:
                yield encode_sse(
                    "clarification",
                    {
                        "thread_id": thread_id,
                        "mode": "clarification",
                        "data": {"question": question},
                    },
                )
                return

            state = state_snapshot.values or {}
            response = build_chat_response(state, request, thread_id, status="success")
            yield encode_sse(
                "final",
                {
                    "thread_id": thread_id,
                    "mode": "final",
                    "data": response.model_dump(),
                },
            )
        except Exception as exc:
            logger.exception("Chat stream failed for thread_id=%s", thread_id)
            yield encode_sse(
                "error",
                {
                    "thread_id": thread_id,
                    "mode": "error",
                    "data": {"message": str(exc)},
                },
            )
        finally:
            await cleanup_runtime(graph)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/execution/{thread_id}")
async def get_execution_history(thread_id: str):
    graph = None
    try:
        graph = await build_graph(init_mcp=False)
        config = {"configurable": {"thread_id": thread_id}}
        state_snapshot = await graph.aget_state(config)

        if not state_snapshot or not state_snapshot.values:
            raise HTTPException(status_code=404, detail="会话不存在")

        state = state_snapshot.values
        return {
            "thread_id": thread_id,
            "query": state.get("original_query"),
            "plan": state.get("plan"),
            "step_results": [
                item.model_dump()
                for item in (serialize_step_results(state.get("step_results")) or [])
            ],
            "execution_summary": serialize_execution_summary(state.get("execution_summary")),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Get execution history failed for thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        await cleanup_runtime(graph)


@app.get("/execution/{thread_id}/step/{step_index}")
async def get_step_detail(thread_id: str, step_index: int):
    try:
        history = await get_execution_history(thread_id)
        steps = history.get("step_results", [])
        matching_steps = [step for step in steps if step["step_index"] == step_index]

        if not matching_steps:
            raise HTTPException(status_code=404, detail=f"步骤 {step_index} 不存在")

        return matching_steps[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
