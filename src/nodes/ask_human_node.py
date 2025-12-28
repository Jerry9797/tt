from langgraph.types import Command, interrupt
from src.graph_state import AgentState

def ask_human(state: AgentState):
    from langchain_core.messages import AIMessage, HumanMessage

    # ⭐ 获取中断上下文
    return_to = state.get("return_to", {})
    question = state.get("response")
    source_node = "query_rewrite_node"


    print(f"[AskHuman] 中断来源: {source_node}")
    print(f"[AskHuman] 问题: {question}")
    print(f"[AskHuman] 将返回到: {return_to}")

    # ⭐ 挂起执行，等待用户输入
    user_response = interrupt(question)

    print(f"[AskHuman] 收到用户回复: {user_response}")

    # ⭐ 构造消息记录
    new_messages = [
        AIMessage(content=f"⏸️ {question}"),
        HumanMessage(content=user_response)
    ]

    # ⭐ 统一返回：使用human_input存储用户输入
    update_dict = {
        "messages": new_messages,
        "need_clarification": False   # 清除中断状态
    }

    print(f"[AskHuman] 返回到节点: {return_to}")

    # ⭐ 返回到interrupt_context指定的节点
    return Command(
        goto=return_to,
        update=update_dict
    )