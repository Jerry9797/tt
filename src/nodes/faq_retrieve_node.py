from src.utils.qdrant_utils import qdrant_select
from src.graph_state import AgentState

def faq_retrieve_node(state: AgentState):
    query_faq = state['faq_query']
    results = qdrant_select(query_faq, collection_name="dz_channel_faq")
    return {"faq_response": "\n".join(results.points)}
