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
graph = build_graph()

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        config = {"configurable": {"thread_id": request.thread_id or "default_thread"}}

        # 1. 处理恢复逻辑
        if request.resume_input:
            # 获取当前状态
            state_snapshot = graph.get_state(config)
            
            # 从状态中获取之前生成的澄清问题 (作为 AIMessage)
            previous_question = state_snapshot.values.get("response")
            
            # 构造新的对话记录: AI的提问 + 用户的回答
            new_messages = [
                AIMessage(content=previous_question or ""),
                HumanMessage(content=request.resume_input)
            ]
            
            # 更新状态: 将新消息追加到 messages 列表
            graph.update_state(config, {"messages": new_messages})
            
            # 恢复执行 (输入为 None，因为状态已更新)
            result = graph.invoke(None, config=config)
            
        else:
            # 2. 处理新请求
            initial_state = AgentState()
            initial_state['query'] = request.query
            initial_state['plan'] = []
            initial_state['current_step'] = 0
            initial_state['past_steps'] = []
            
            # 处理历史消息 (History 仅在第一次请求时需要在 API 层处理，后续都在 state 中)
            messages = []
            for msg in request.history:
                if msg.get('role') == 'user':
                    messages.append(HumanMessage(content=msg.get('content')))
                elif msg.get('role') == 'assistant':
                    messages.append(AIMessage(content=msg.get('content')))
            initial_state['messages'] = messages

            # 执行 Graph
            result = graph.invoke(initial_state, config=config)

        # 3. 检查是否中断 (interrupt_before 生效)
        state_snapshot = graph.get_state(config)
        # 检查下一个要执行的节点是否是 ask_human
        if state_snapshot.next and "ask_human" in state_snapshot.next:
             # 获取澄清问题 (由 query_rewrite_node 设置在 response 字段)
             question = state_snapshot.values.get("response")
             return ChatResponse(
                response=question,
                thread_id=config["configurable"]["thread_id"],
                status="need_clarification"
             )

        # 4. 正常结束
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
