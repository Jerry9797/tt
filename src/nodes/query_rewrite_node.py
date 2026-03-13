from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable

from src.config.llm import get_gpt_model
from src.graph_state import AgentState
from src.prompt.prompt_loader import get_prompt

async def query_rewrite_node(state: AgentState):
    print("query_rewrite_node 开始运行...")
    original_query = state['original_query']
    print("Original query:", original_query)
    history = state.get('messages', [])
    history_str = "\n".join([f"{msg.type}: {msg.content}" for msg in history]) if history else ""
    effective_query = original_query

    # 恢复澄清后，将用户补充信息直接并入当前查询，降低模型二次追问概率。
    for msg in reversed(history):
        if getattr(msg, "type", "") == "human" and getattr(msg, "content", ""):
            clarification = msg.content.strip()
            if clarification and clarification not in original_query:
                effective_query = f"{original_query}\n补充信息：{clarification}"
            break

    query_rewrite_prompt = ChatPromptTemplate.from_template(
        get_prompt("query_rewrite")
    )

    chain : Runnable = (
            query_rewrite_prompt
            | get_gpt_model("gpt-4.1-mini")
            | JsonOutputParser()
    )

    # chain = query_rewrite_prompt | q_plus | JsonOutputParser()
    ret = await chain.ainvoke({"query": effective_query, "history": history_str})

    if ret.get("need_clarification"):
        print(f"需要澄清: {ret.get('clarifying_question')}")
        return {
            "need_clarification": ret.get("need_clarification"),
            "response": ret.get("clarifying_question"),
            "return_to": "query_rewrite_node",
            "rewritten_query": original_query,
            "keywords": ret.get("keywords", [])
        }

    return {
        "need_clarification": False,
        "rewritten_query": ret.get("rewritten_query", original_query),
        "keywords": ret.get("keywords", [])
    }
