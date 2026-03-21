import logging

from langgraph.types import Command, interrupt
from src.graph_state import AgentState

logger = logging.getLogger(__name__)


async def ask_human(state: AgentState):
    from langchain_core.messages import AIMessage, HumanMessage

    # `ask_human` 是所有澄清流程的统一挂起点。
    # 它本身不关心为什么要问，只关心：
    # 1. 问什么（clarification_question）
    # 2. 问完之后回到哪里（resume_target）
    return_to = state.get("resume_target") or "query_rewrite_node"
    question = state.get("clarification_question")
    source_node = return_to


    logger.info("Interrupt from node=%s will resume to node=%s", source_node, return_to)

    # ⭐ 挂起执行，等待用户输入
    user_response = interrupt(question)

    # 把“系统发出的澄清问题 + 用户补充的回复”都写回消息历史。
    # 后续节点既可以直接消费 `resume_input`，也可以在 prompt 中看到完整对话。
    new_messages = [
        AIMessage(content=f"⏸️ {question}"),
        HumanMessage(content=user_response)
    ]

    # 从这里开始，中断态被消费完成：
    # - `awaiting_user_input` 复位
    # - `clarification_question` / `resume_target` 清空
    # - 用户新回复放进 `resume_input`，交给目标节点消费一次
    update_dict = {
        "messages": new_messages,
        "awaiting_user_input": False,
        "clarification_question": None,
        "resume_target": None,
        "resume_input": user_response,
    }

    # ⭐ 返回到interrupt_context指定的节点
    return Command(
        goto=return_to,
        update=update_dict
    )
