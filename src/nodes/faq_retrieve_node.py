from src.utils.qdrant_utils import qdrant_select
from src.graph_state import AgentState

async def faq_retrieve_node(state: AgentState):
    rewritten_query = state.get("rewritten_query") or state.get("original_query")
    if not rewritten_query or state.get("need_clarification"):
        return {"faq_response": None}

    try:
        results = qdrant_select(rewritten_query, collection_name="dz_channel_faq")
    except Exception as e:
        print(f"[FAQ Retrieve] Qdrant 查询失败，跳过 FAQ 召回: {e}")
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
