from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

from src.config.redis import client
from src.config.mysql import get_connection, get_connection_string
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

async def build_graph(init_mcp: bool = True):
    # ⭐ 初始化 MCP 工具管理器（异步）
    if init_mcp:
        import asyncio
        from src.mcp import init_mcp_manager
        
        try:
            await init_mcp_manager()
            # print("[Graph] MCP 管理器初始化完成")
        except Exception as e:
            print(f"[Graph] MCP 初始化失败: {e}，继续使用非 MCP 工具")
    
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
    import aiomysql
    
    conn_str = await get_connection_string()
    # 解析连接参数
    db_params = AIOMySQLSaver.parse_conn_string(conn_str)
    try:
        conn = await aiomysql.connect(**db_params, autocommit=True)
        checkpointer = AIOMySQLSaver(conn=conn)
        # print(f"[Graph] Initialized AIOMySQLSaver with aiomysql connection")
    except Exception as e:
        print(f"[Graph] Failed to connect to MySQL via aiomysql: {e}")
        raise e

    # Store 暂时使用内存
    store_arg = True

    return graph.compile(checkpointer=checkpointer, store=store_arg)

if __name__ == '__main__':
    # Simple test to verify graph compilation
    try:
        graph = build_graph()
        print("Graph built successfully.")
    except Exception as e:
        print(f"Graph build failed: {e}")
