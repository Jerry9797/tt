from fastapi import FastAPI, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

from src.graph_state import AgentState
from src.nodes.build_graph import build_graph

app = FastAPI(
    title="TT Assistant API",
    description="TT Assistant API",
    version="v0.1",
)

from langchain_core.messages import HumanMessage, AIMessage

# Request Model
class ChatRequest(BaseModel):
    query: Optional[str] = None
    thread_id: Optional[str] = None
    resume_input: Optional[str] = None
    history: Optional[List[dict]] = []

# Step Result Response Model
class StepResultResponse(BaseModel):
    """步骤结果响应"""
    step_index: int
    description: str
    status: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[float] = None
    output: Optional[str] = None
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = []

# Response Model
class ChatResponse(BaseModel):
    query: Optional[str] = None
    intent: Optional[str] = None
    faq_response: Optional[str] = None
    plan: Optional[List[str]] = None
    response: Optional[str] = None
    thread_id: Optional[str] = None
    status: str = "success"
    
    # ⭐ 新增: 步骤执行结果
    step_results: Optional[List[StepResultResponse]] = None
    
    # ⭐ 新增: 执行摘要
    execution_summary: Optional[Dict[str, Any]] = None

# Initialize graph


from langgraph.errors import GraphInterrupt

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    graph = None
    try:
        graph = await build_graph()
        config = {"configurable": {"thread_id": request.thread_id or "default_thread"}}
        result = {} # Initialize result

        # 1. 检查是否是 "Resume" (Clarification Response)
        if request.resume_input:
            print(f"中断恢复: {request.resume_input}")
            # 使用 Command 恢复中断
            # 注意: ainvoke 可能会因为再次中断而抛出 GraphInterrupt 或直接返回
            try:
                result = await graph.ainvoke(Command(resume=request.resume_input), config=config)
            except GraphInterrupt:
                print("Graph execution interrupted (resume).")
            
        else:
            print("TT running...")
            # 2. 处理新请求
            initial_state = AgentState()
            initial_state['query'] = request.query
            initial_state['plan'] = []
            initial_state['current_step'] = 0
            initial_state['past_steps'] = []
            
            # 处理历史消息
            messages = []
            for msg in request.history:
                if msg.get('role') == 'user':
                    messages.append(HumanMessage(content=msg.get('content')))
                elif msg.get('role') == 'assistant':
                    messages.append(AIMessage(content=msg.get('content')))
            initial_state['messages'] = messages

            # 执行 Graph（异步）
            try:
                result = await graph.ainvoke(initial_state, config=config)
            except GraphInterrupt:
                print("Graph execution interrupted (new request).")

        # 3. 检查是否中断 (Generic Interrupt)
        # ⭐ 使用 aget_state (异步)
        state_snapshot = await graph.aget_state(config)
        tasks = list(state_snapshot.tasks)
        if tasks and tasks[0].interrupts:
            # 获取中断信息
            interrupt_value = tasks[0].interrupts[0].value
            question = interrupt_value if isinstance(interrupt_value, str) else interrupt_value.get("question", str(interrupt_value))
            
            return ChatResponse(
                response=question,
                thread_id=config["configurable"]["thread_id"],
                status="need_clarification"
            )

        # 4. 正常结束 (只有在没有中断时才返回结果)
        # 如果 result 为空且没有中断，说明出现了异常情况
        if result is None:
            # 如果是 ainvoke 返回 None，可能是状态未改变或其他原因
            result = {}
            if state_snapshot and state_snapshot.values:
                # 尝试从最新状态中获取结果，如果 ainvoke 没有返回完整状态
                result = state_snapshot.values
        
        # 转换步骤结果
        step_results_response = None
        if "step_results" in result and result["step_results"]:
            step_results_response = [
                StepResultResponse(
                    step_index=r.step_index,
                    description=r.step_description,
                    status=r.status.value if hasattr(r.status, 'value') else str(r.status),
                    start_time=r.start_time.isoformat() if r.start_time else None,
                    end_time=r.end_time.isoformat() if r.end_time else None,
                    duration_ms=r.duration_ms,
                    output=r.output_result,
                    error=r.error_message,
                    tool_calls=[{
                        "tool_name": tc.tool_name,
                        "arguments": tc.arguments,
                        "result": str(tc.result) if tc.result else None,
                        "error": tc.error,
                        "duration_ms": tc.duration_ms
                    } for tc in r.tool_calls]
                )
                for r in result["step_results"]
            ]
        
        # 转换执行摘要
        execution_summary_response = None
        if "execution_summary" in result and result["execution_summary"]:
            summary = result["execution_summary"]
            execution_summary_response = {
                "plan_id": summary.plan_id,
                "query": summary.query,
                "intent": summary.intent,
                "is_sop": summary.is_sop,
                "total_steps": summary.total_steps,
                "completed_steps": summary.completed_steps,
                "failed_steps": summary.failed_steps,
                "overall_status": summary.overall_status.value if hasattr(summary.overall_status, 'value') else str(summary.overall_status),
                "total_duration_ms": summary.total_duration_ms,
                "start_time": summary.start_time.isoformat() if summary.start_time else None,
                "end_time": summary.end_time.isoformat() if summary.end_time else None
            }

        return ChatResponse(
            query=result.get("faq_query", request.query), 
            intent=result.get("intent"),
            faq_response=result.get("faq_response"),
            plan=result.get("plan"),
            response=result.get("response"),
            thread_id=config["configurable"]["thread_id"],
            status="success",
            step_results=step_results_response,
            execution_summary=execution_summary_response
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 显式关闭数据库连接，防止 loop closed error
        if graph and hasattr(graph.checkpointer, 'conn'):
            try:
                graph.checkpointer.conn.close()
            except Exception as e:
                print(f"Error closing DB connection: {e}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/execution/{thread_id}")
async def get_execution_history(thread_id: str):
    """查询某个会话的执行历史"""
    try:
        graph = build_graph()
        config = {"configurable": {"thread_id": thread_id}}
        # ⭐ 使用 aget_state (异步)
        state_snapshot = await graph.aget_state(config)
        
        if not state_snapshot or not state_snapshot.values:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        state = state_snapshot.values
        step_results = state.get("step_results", [])
        execution_summary = state.get("execution_summary")
        
        return {
            "thread_id": thread_id,
            "query": state.get("query"),
            "plan": state.get("plan"),
            "step_results": [
                {
                    "step_index": r.step_index,
                    "description": r.step_description,
                    "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
                    "start_time": r.start_time.isoformat() if r.start_time else None,
                    "end_time": r.end_time.isoformat() if r.end_time else None,
                    "duration_ms": r.duration_ms,
                    "output": r.output_result,
                    "error": r.error_message,
                    "tool_calls": [{
                        "tool_name": tc.tool_name,
                        "arguments": tc.arguments,
                        "result": str(tc.result) if tc.result else None,
                        "error": tc.error,
                        "duration_ms": tc.duration_ms
                    } for tc in r.tool_calls]
                }
                for r in step_results
            ],
            "execution_summary": {
                "plan_id": execution_summary.plan_id,
                "query": execution_summary.query,
                "intent": execution_summary.intent,
                "is_sop": execution_summary.is_sop,
                "total_steps": execution_summary.total_steps,
                "completed_steps": execution_summary.completed_steps,
                "failed_steps": execution_summary.failed_steps,
                "overall_status": execution_summary.overall_status.value if hasattr(execution_summary.overall_status, 'value') else str(execution_summary.overall_status),
                "total_duration_ms": execution_summary.total_duration_ms,
                "start_time": execution_summary.start_time.isoformat() if execution_summary.start_time else None,
                "end_time": execution_summary.end_time.isoformat() if execution_summary.end_time else None
            } if execution_summary else None
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/execution/{thread_id}/step/{step_index}")
async def get_step_detail(thread_id: str, step_index: int):
    """查询某个步骤的详细信息"""
    try:
        history = await get_execution_history(thread_id)
        
        steps = history.get("step_results", [])
        matching_steps = [s for s in steps if s["step_index"] == step_index]
        
        if not matching_steps:
            raise HTTPException(status_code=404, detail=f"步骤 {step_index} 不存在")
        
        return matching_steps[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
