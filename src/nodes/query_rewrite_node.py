import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable

from src.config.llm import get_gpt_model, mt_llm
from src.graph_state import AgentState
from src.prompt.prompt_loader import get_prompt

logger = logging.getLogger(__name__)

async def query_rewrite_node(state: AgentState):
    original_query = state['original_query']
    history = state.get('messages', [])
    history_str = "\n".join([f"{msg.type}: {msg.content}" for msg in history]) if history else ""
    effective_query = original_query
    resume_input = state.get("resume_input")

    # 如果当前是从 ask_human 恢复回来，优先使用显式的 `resume_input`。
    # 这样 query rewrite 不需要依赖“去消息历史里猜哪一句是最新补充”。
    if resume_input and resume_input not in original_query:
        effective_query = f"{original_query}\n补充信息：{resume_input}"

    # 非恢复场景下，仍然兼容从历史里抽取最近一条用户补充信息。
    # 这能让多轮会话中的“补一句说明”自然参与改写，而不要求上游显式传参。
    if not resume_input:
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
            | mt_llm("gpt-4.1-mini")
            | JsonOutputParser()
    )

    # chain = query_rewrite_prompt | q_plus | JsonOutputParser()
    ret = await chain.ainvoke({"query": effective_query, "history": history_str})

    if ret.get("need_clarification"):
        logger.info("Query rewrite requires clarification")
        return {
            # 一旦需要澄清，只写入中断态字段，不再复用最终输出字段。
            "awaiting_user_input": bool(ret.get("need_clarification")),
            "clarification_question": ret.get("clarifying_question"),
            "resume_target": "query_rewrite_node",
            # 恢复输入由 ask_human 在下一轮写入；这里先清空，避免旧值污染。
            "resume_input": None,
            "rewritten_query": original_query,
            "keywords": ret.get("keywords", [])
        }

    return {
        # 改写成功后，统一清理中断态，保证后续节点看到的是“干净状态”。
        "awaiting_user_input": False,
        "clarification_question": None,
        "resume_target": None,
        "resume_input": None,
        "rewritten_query": ret.get("rewritten_query", original_query),
        "keywords": ret.get("keywords", [])
    }
