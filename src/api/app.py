from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional, Any

from src.graph_state import AgentState
from src.nodes import build_graph

app = FastAPI(
    title="TT Assistant API",
    description="TT Assistant API",
    version="v0.1",
)

# Request Model
class ChatRequest(BaseModel):
    query: str
    history: Optional[List[dict]] = []

# Response Model
class ChatResponse(BaseModel):
    query: str
    intent: Optional[str] = None
    faq_response: Optional[str] = None
    plan: Optional[List[str]] = None
    response: Optional[str] = None
    status: str = "success"

# Initialize graph
graph = build_graph()

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # 舒适话state
        initial_state = AgentState()
        initial_state['query'] = request.query
        initial_state['plan'] = []
        initial_state['current_step'] = 0
        initial_state['completed_steps'] = []

        # Invoke the graph
        result = graph.invoke(initial_state)

        if "" in result.get("response")[-1]:
            # 询问用户
            pass

        # Prepare response
        return ChatResponse(
            query=result.get("query", request.query),
            intent=result.get("intent"),
            faq_response=result.get("faq_response"),
            plan=result.get("plan"),
            response=result.get("response"),
            status="success"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
