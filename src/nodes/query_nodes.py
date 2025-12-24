from typing import Literal, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command, interrupt

from src.config.llm import q_plus
from src.graph_state import AgentState
from src.prompt.prompt import get_query_rewrite_prompt

query_rewrite_prompt = ChatPromptTemplate.from_template(
    get_query_rewrite_prompt()
)

def query_rewrite_node(state: AgentState):
    print("query_rewrite_node 开始运行...")
    query = state['query']
    history = state.get('messages', [])
    history_str = "\n".join([f"{msg.type}: {msg.content}" for msg in history]) if history else ""
    
    print(f"DEBUG: [query_rewrite] History length: {len(history_str)}")
    print(f"DEBUG: [query_rewrite] Current History Msg Count: {len(history)}")

    chain = query_rewrite_prompt | q_plus | JsonOutputParser()
    ret = chain.invoke({"query": query, "history": history_str})

    if ret.get("need_clarification"):
        print(f"需要澄清: {ret.get('clarifying_question')}")
        return Command(goto="ask_human", update={
            "need_clarification": ret.get("need_clarification"),
            "response": ret.get("clarifying_question"),
            "return_to": "query_rewrite_node",
            "faq_query": "",
            "keywords": []
        })

    return {
        "faq_query": ret.get("rewritten_query", query),
        "keywords": ret.get("keywords", [])
    }

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
