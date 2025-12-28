from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
# from langgraph.checkpoint.redis import RedisSaver # Optional: keep if needed for reference, but we are switching to MySQL
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from langgraph.store.mysql import PyMySQLStore

from src.config.redis import client
from src.config.mysql import get_connection
from src.utils.mysql_store import MySQLStore
from src.graph_state import AgentState
from src.nodes.query_rewrite_node import query_rewrite_node
from src.nodes.ask_human_node import ask_human
from src.nodes.faq_retrieve_node import faq_retrieve_node
from src.nodes.sop_match_node import sop_match_node
from src.nodes.plan_nodes import planning_node, plan_executor_node, replan_node

# Global persistence instances
_checkpointer = None
_store = None

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("query_rewrite_node", query_rewrite_node)
    graph.add_node("ask_human", ask_human)

    graph.add_node("faq_retrieve_node", faq_retrieve_node)
    graph.add_node("sop_match_node", sop_match_node)
    graph.add_node("planning_node", planning_node)
    graph.add_node("plan_executor_node", plan_executor_node)
    graph.add_node("replan_node", replan_node)

    # edge
    graph.set_entry_point("query_rewrite_node")

    # query_rewrite_node 默认连向 faq_retrieve_node
    # 跳转到 ask_human 的边通过 Command 动态处理
    graph.add_edge("query_rewrite_node", "faq_retrieve_node")

    graph.add_edge("faq_retrieve_node", "sop_match_node")

    def router_plan(state):
        if state.get("is_sop_matched"):
            return "plan_executor_node"
        return "planning_node"

    graph.add_conditional_edges("sop_match_node", router_plan,
                                {
                                    "planning_node": "planning_node",
                                    "plan_executor_node": "plan_executor_node",
                                })

    graph.add_edge("planning_node", "plan_executor_node")
    graph.add_edge("plan_executor_node", "replan_node")

    def router_replan(state: AgentState):
        steps = state.get("plan")
        current_step = state.get("current_step")
        if current_step < len(steps):
            return "plan_executor_node"
        return "end"

    graph.add_conditional_edges("replan_node", router_replan,
                                {
                                    "plan_executor_node": "plan_executor_node",
                                    "end": END,
                                })

    # Initialize persistence
    global _checkpointer, _store
    
    if _checkpointer is None:
        if PyMySQLSaver:
            try:
                # Create dedicated connections for checkpointer and store
                conn_cp = get_connection()
                _checkpointer = PyMySQLSaver(conn_cp)
                _checkpointer.setup()
                print("[Graph] Initialized MySQL Checkpointer")
            except Exception as e:
                print(f"[Graph] Failed to initialize MySQL Checkpointer: {e}")
                _checkpointer = MemorySaver()
        else:
            _checkpointer = MemorySaver()
            print("[Graph] Initialized MemorySaver (MySQL module missing)")
            
    if _store is None:
        try:
            # MySQLStore handles its own connection creation if not provided, 
            # but we can pass one to be explicit or use the same config.
            # We'll let it create its own using the config defaults.
            _store = MySQLStore() 
            print("[Graph] Initialized MySQL Store")
        except Exception as e:
            print(f"[Graph] Failed to initialize MySQL Store: {e}")
            # Fallback to simple in-memory store if needed, or None
            # graph.compile(store=...) usually accepts a BaseStore. 
            # If failed, we might pass True (MemoryStore) or None.
            _store = None # Let LangGraph use default compatible store or raise error
            # Or use InMemoryStore if available? LangGraph defaults to in-memory if store=True?
            # actually store=True enables InMemoryStore.
            
    # If store init failed, pass True to fallback to InMemory, or pass None to disable?
    # Original code had store=True.
    store_arg = _store if _store else True

    return graph.compile(checkpointer=_checkpointer, store=store_arg)

if __name__ == '__main__':
    # Simple test to verify graph compilation
    try:
        graph = build_graph()
        print("Graph built successfully.")
    except Exception as e:
        print(f"Graph build failed: {e}")
