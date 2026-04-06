import operator

from pydantic import BaseModel, Field
from typing import Annotated, List, Optional, Required, TypedDict, Union
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from src.models.execution_result import PlanExecutionSummary, StepExecutionResult


def overwrite(left, right):
    """LangGraph reducer: 对标量/单值字段始终以后一次更新覆盖前一次。"""
    return right


class AgentState(TypedDict, total=False):
    """
    LangGraph 全局状态。

    设计原则：
    1. 请求上下文、执行态、中断态、输出态分开命名，避免一个字段承担多个语义。
    2. `messages` / `step_results` 这类“追加型”字段使用 reducer 聚合。
    3. 其余字段尽量保持单值语义，由最新节点直接覆盖。
    4. `total=False` 配合 `Required[...]` 使用，表示：运行时允许渐进式补齐字段，
       但真正的最小初始状态仍然有明确约束。
    """

    # 请求上下文：这些字段描述用户问题本身，以及问题在图中的语义化结果。
    # `original_query`
    # 字面意思：用户最初输入的原始问题。
    # 作用：作为整条链路的稳定输入，避免后续改写覆盖原始问题。
    original_query: Required[str]
    # `messages`
    # 字面意思：当前会话累计的消息列表。
    # 作用：给后续节点和模型提供上下文，支持多轮对话、工具消息和人工澄清历史。
    messages: Required[Annotated[List[AnyMessage], add_messages]]
    # `plan`
    # 字面意思：当前待执行的步骤列表。
    # 作用：作为 workflow 的执行主干，驱动 plan_executor 按顺序处理任务。
    plan: Required[Annotated[List[str], overwrite]]
    # `current_step`
    # 字面意思：当前执行到的步骤下标。
    # 作用：标记 plan 的推进进度，并决定下一轮执行哪个步骤。
    current_step: Required[Annotated[int, overwrite]]

    # `rewritten_query`
    # 字面意思：在原始问题基础上补充上下文后的改写版本。
    # 作用：提供给 FAQ 检索、SOP 匹配、planning 等节点作为更适合检索和推理的输入。
    rewritten_query: Annotated[str, overwrite]
    # `faq_response`
    # 字面意思：FAQ 召回结果，统一存成字符串。
    # 作用：作为可直接展示或继续传给后续节点参考的 FAQ 上下文。
    faq_response: Annotated[Optional[str], overwrite]
    # `intent`
    # 字面意思：识别出的业务意图标签。
    # 作用：告诉后续节点“这类问题属于什么场景”，用于选 SOP、选 prompt 或统计分类。
    intent: Annotated[Optional[str], overwrite]
    # `keywords`
    # 字面意思：从 query rewrite 提取出的关键词。
    # 作用：辅助检索增强，也方便调试时观察模型抓取了哪些核心信息。
    keywords: Annotated[List[str], overwrite]

    # 执行态：描述 plan 执行过程及其结构化产物。
    # `step_results`
    # 字面意思：每个步骤的结构化执行结果列表。
    # 作用：沉淀步骤级状态、输出、耗时、工具调用等信息，方便调试、汇总和 UI 展示。
    step_results: Annotated[List[StepExecutionResult], operator.add]
    # `execution_summary`
    # 字面意思：整个执行过程的最终摘要。
    # 作用：把 step_results 汇总成面向接口和前端的总览信息，避免调用方自己再做二次聚合。
    execution_summary: Annotated[Optional[PlanExecutionSummary], overwrite]
    # `human_question`
    # 字面意思：当前等待用户补充的问题。
    # 作用：由业务节点声明，统一交给 ask_human_node 触发中断。
    human_question: Annotated[Optional[str], overwrite]
    # `human_resume_node`
    # 字面意思：用户回答后应回到的节点名。
    # 作用：ask_human_node 恢复后据此跳回原业务节点。
    human_resume_node: Annotated[Optional[str], overwrite]
    # 输出态：只表示最终面向用户的答案，不再复用为澄清问题。
    # `final_response`
    # 字面意思：最终生成给用户的回复文本。
    # 作用：作为成功路径的最终输出，供 API 返回和前端直接展示。
    final_response: Annotated[Optional[str], overwrite]


class Plan(BaseModel):
    steps: List[str] = Field(description="遵循的不同步骤，应按顺序排列")


class Response(BaseModel):
    """Response to user."""

    response: str
    model_config = {
        "arbitrary_types_allowed": True
    }


class Act(BaseModel):
    """Action to perform."""

    action: Union[Response, Plan] = Field(
        description="Action to perform. If you want to respond to user, use Response. "
        "If you need to further use tools to get the answer, use Plan."
    )
    model_config = {
        "arbitrary_types_allowed": True
    }
