from src.utils.qdrant_utils import qdrant_select
from src.graph_state import AgentState

async def faq_retrieve_node(state: AgentState):
    query_faq = state['faq_query']
    # 注意：如果 qdrant_select 不支持异步，可能需要使用 asyncio.to_thread
    results = qdrant_select(query_faq, collection_name="dz_channel_faq")
    return {"faq_response": "\n".join(results.points)}

