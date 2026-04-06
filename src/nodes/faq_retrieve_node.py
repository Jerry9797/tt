import logging

from src.utils.qdrant_utils import qdrant_select
from src.utils.state_utils import get_effective_query
from src.graph_state import AgentState

logger = logging.getLogger(__name__)


async def faq_retrieve_node(state: AgentState):
    rewritten_query = get_effective_query(state)
    if not rewritten_query:
        return {"faq_response": None}

    try:
        results = qdrant_select(rewritten_query, collection_name="dz_channel_faq")
    except Exception as e:
        logger.warning("Qdrant query failed, skip FAQ retrieval: %s", e)
        return {"faq_response": None}

    faq_items = []
    for point in getattr(results, "points", []) or []:
        payload = getattr(point, "payload", {}) or {}
        answer = payload.get("answer")
        question = payload.get("question")
        if answer:
            faq_items.append(answer)
        elif question:
            faq_items.append(question)

    return {"faq_response": "\n".join(faq_items) if faq_items else None}
