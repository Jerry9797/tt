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
