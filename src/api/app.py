from fastapi import FastAPI, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel
from typing import List, Optional, Any

from src.graph_state import AgentState
from src.nodes.node import build_graph

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

# Response Model
class ChatResponse(BaseModel):
    query: Optional[str] = None
    intent: Optional[str] = None
    faq_response: Optional[str] = None
    plan: Optional[List[str]] = None
    response: Optional[str] = None
    thread_id: Optional[str] = None
    status: str = "success"

# Initialize graph


from langgraph.errors import GraphInterrupt

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        graph = build_graph()
        config = {"configurable": {"thread_id": request.thread_id or "default_thread"}}
        result = {} # Initialize result

        # 1. 处理恢复逻辑
        if request.resume_input:
            print(f"中断恢复: {request.resume_input}")
            # 使用 Command 恢复中断
            # 注意: invoke 可能会因为再次中断而抛出 GraphInterrupt 或直接返回
            try:
                result = graph.invoke(Command(resume=request.resume_input), config=config)
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

            # 执行 Graph
            try:
                result = graph.invoke(initial_state, config=config)
            except GraphInterrupt:
                print("Graph execution interrupted (new request).")

        # 3. 检查是否中断 (Generic Interrupt)
        state_snapshot = graph.get_state(config)
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
            result = {}

        return ChatResponse(
            query=result.get("faq_query", request.query), 
            intent=result.get("intent"),
            faq_response=result.get("faq_response"),
            plan=result.get("plan"),
            response=result.get("response"),
            thread_id=config["configurable"]["thread_id"],
            status="success"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
