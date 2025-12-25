"""
Graph Construction Module
Aggregates nodes from sub-modules and builds the state graph.
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.redis import RedisSaver

from src.config.redis import client
from src.graph_state import AgentState
from src.nodes.query_nodes import query_rewrite_node, ask_human
from src.nodes.rag_nodes import faq_retrieve_node
from src.nodes.intent_nodes import sop_match_node
from src.nodes.plan_nodes import planning_node, plan_executor_node, replan_node

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
    
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)

if __name__ == '__main__':
    # Simple test to verify graph compilation
    try:
        graph = build_graph()
        print("Graph built successfully.")
    except Exception as e:
        print(f"Graph build failed: {e}")
