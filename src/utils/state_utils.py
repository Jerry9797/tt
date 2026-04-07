from src.graph_state import AgentState


def get_effective_query(state: AgentState) -> str:
    """优先使用改写后的 query，降级到原始 query。"""
    return state.get("rewritten_query") or state.get("original_query", "")
