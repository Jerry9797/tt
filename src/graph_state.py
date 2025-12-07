from pydantic import BaseModel, Field
from typing import TypedDict, Annotated, List, Dict, Any
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    query: str
    # 消息
    messages: Annotated[List[AnyMessage], add_messages]
    # 对query进行提取，查询FAQ
    faq_query: str
    faq_response: list[str]
    # 意图
    intent: str
    # 是否命中SOP
    is_sop_matched: bool
    # 计划
    plan: List[str]
    # 当前执行的步骤
    current_step: int
    # 以及执行完成的步骤
    completed_steps: List[str]
    response: str


class Plan(BaseModel):
    steps: List[str] = Field(description="遵循的不同步骤，应按顺序排列")