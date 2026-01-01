import operator

from pydantic import BaseModel, Field
from typing import TypedDict, Annotated, List, Dict, Any, Union, Tuple, Optional
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from requests.models import Response

# 导入执行结果模型
from src.models.execution_result import StepExecutionResult, PlanExecutionSummary


def overwrite(left, right):
    return right

class AgentState(TypedDict):
    original_query: str
    rewritten_query: str
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
    plan: Annotated[List[str], overwrite]
    # 当前执行的步骤
    current_step: Annotated[int, overwrite]
    # 以及执行完成的步骤
    past_steps: Annotated[List[Tuple], operator.add]
    response: str
    
    # ⭐ 新增: 结构化的执行结果列表
    step_results: Annotated[List[StepExecutionResult], operator.add]
    
    # ⭐ 新增: 当前正在执行的步骤结果
    current_step_result: Annotated[Optional[StepExecutionResult], overwrite]
    
    # ⭐ 新增: 整体执行摘要
    execution_summary: Annotated[Optional[PlanExecutionSummary], overwrite]
    
    # ⭐ 新增: Human-in-the-Loop 通用字段
    need_clarification: Annotated[bool, overwrite] # 是否中断
    return_to: Annotated[str, overwrite] # 发出中断请求的node



class Plan(BaseModel):
    steps: List[str] = Field(description="遵循的不同步骤，应按顺序排列")


class Act(BaseModel):
    """Action to perform."""
    action: Union[Response, Plan] = Field(
        description="Action to perform. If you want to respond to user, use Response. "
        "If you need to further use tools to get the answer, use Plan."
    )
    model_config = {
        "arbitrary_types_allowed": True
    }

class Response(BaseModel):
    """Response to user."""
    response: str
    model_config = {
        "arbitrary_types_allowed": True
    }