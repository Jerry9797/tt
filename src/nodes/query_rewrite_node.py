import json
import logging
import re

from langchain_core.messages import SystemMessage
from langgraph.types import Command

from src.config.llm import get_gpt_model
from src.graph_state import AgentState
from src.prompt.prompt_loader import get_prompt

logger = logging.getLogger(__name__)


def _extract_json_payload(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group())


def _get_latest_human_message(state: AgentState, original_query: str) -> str:
    for msg in reversed(state.get("messages", [])):
        if getattr(msg, "type", "") != "human":
            continue
        content = getattr(msg, "content", "")
        if not isinstance(content, str):
            continue
        clarification = content.strip()
        if clarification and clarification not in original_query:
            return clarification
    return ""


async def query_rewrite_node(state: AgentState):
    original_query = state["original_query"]
    history = state.get("messages", [])

    history_parts = ["{}: {}".format(msg.type, msg.content) for msg in history]
    history_str = "\n".join(history_parts) if history_parts else ""

    clarification = _get_latest_human_message(state, original_query)
    if clarification:
        effective_query = original_query + "\n补充信息：" + clarification
    else:
        effective_query = original_query

    prompt = get_prompt("query_rewrite").format(query=effective_query, history=history_str)
    response = await get_gpt_model("gpt-4.1-mini").ainvoke([SystemMessage(content=prompt)])
    ret = _extract_json_payload(response.content)

    if ret.get("need_clarification"):
        question = ret.get("clarifying_question") or "请补充问题相关信息"
        logger.info("Query rewrite requires clarification: %s", question)
        return Command(
            goto="ask_human_node",
            update={
                "human_question": question,
                "human_resume_node": "query_rewrite_node",
            },
        )

    return {
        "rewritten_query": ret.get("rewritten_query", original_query),
        "keywords": ret.get("keywords", []),
    }
