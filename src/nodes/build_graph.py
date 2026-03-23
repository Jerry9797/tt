import logging
import os
from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
from langgraph.graph import END, StateGraph

from src.config.mysql import get_connection_string
from src.config.sop_loader import get_sop_loader
from src.graph_state import AgentState
from src.nodes.ask_human_node import ask_human
from src.nodes.faq_retrieve_node import faq_retrieve_node
from src.nodes.plan_nodes import (
    finalize_execution_node,
    plan_executor_node,
    planning_node,
    replan_node,
)
from src.nodes.query_rewrite_node import query_rewrite_node
from src.nodes.response_generator_node import response_generator_node
from src.nodes.sop_match_node import sop_match_node
from src.tools import ALL_TOOLS

logger = logging.getLogger(__name__)
sop_loader = get_sop_loader()


async def build_graph(init_mcp: bool = True):
    if init_mcp:
        from src.mcp import init_mcp_manager

        try:
            await init_mcp_manager()
        except Exception as exc:
            logger.warning("MCP initialization failed, falling back to non-MCP tools: %s", exc)

    # ⭐ 在图构建时一次性合并工具，避免循环内重复组装
    from src.mcp import get_mcp_manager
    mcp_tools = get_mcp_manager().get_all_tools()
    merged_tools = ALL_TOOLS + mcp_tools
    logger.info("Merged %s tools (%s static + %s MCP)", len(merged_tools), len(ALL_TOOLS), len(mcp_tools))

    graph = StateGraph(AgentState)
    graph.add_node("query_rewrite_node", query_rewrite_node)
    graph.add_node("ask_human", ask_human)
    graph.add_node("faq_retrieve_node", faq_retrieve_node)
    graph.add_node("sop_match_node", sop_match_node)
    graph.add_node("planning_node", planning_node)
    graph.add_node("plan_executor_node", partial(plan_executor_node, tools=merged_tools))
    graph.add_node("replan_node", replan_node)
    graph.add_node("finalize_execution_node", finalize_execution_node)
    graph.add_node("response_generator", response_generator_node)

    graph.set_entry_point("query_rewrite_node")

    def router_query_rewrite(state: AgentState):
        if state.get("awaiting_user_input"):
            return "ask_human"
        return "faq_retrieve_node"

    graph.add_conditional_edges(
        "query_rewrite_node",
        router_query_rewrite,
        {
            "ask_human": "ask_human",
            "faq_retrieve_node": "faq_retrieve_node",
        },
    )
    graph.add_edge("faq_retrieve_node", "sop_match_node")

    def router_plan(state: AgentState):
        intent = state.get("intent")
        if intent and sop_loader.has_sop(intent):
            return "plan_executor_node"
        return "planning_node"

    graph.add_conditional_edges(
        "sop_match_node",
        router_plan,
        {
            "planning_node": "planning_node",
            "plan_executor_node": "plan_executor_node",
        },
    )

    graph.add_edge("planning_node", "plan_executor_node")
    graph.add_edge("plan_executor_node", "replan_node")

    def router_replan(state: AgentState):
        steps = state.get("plan") or []
        current_step = state.get("current_step", 0)
        if current_step < len(steps):
            return "plan_executor_node"
        return "finalize_execution_node"

    graph.add_conditional_edges(
        "replan_node",
        router_replan,
        {
            "plan_executor_node": "plan_executor_node",
            "finalize_execution_node": "finalize_execution_node",
        },
    )
    graph.add_edge("finalize_execution_node", "response_generator")
    graph.add_edge("response_generator", END)

    checkpointer = await build_checkpointer()
    return graph.compile(checkpointer=checkpointer, store=None)


async def build_checkpointer():
    persistence_backend = os.getenv("LANGGRAPH_CHECKPOINTER", "mysql").lower()
    allow_memory_fallback = os.getenv("ALLOW_MEMORY_CHECKPOINTER_FALLBACK", "false").lower() == "true"

    if persistence_backend == "memory":
        logger.info("Using in-memory LangGraph checkpointer")
        return MemorySaver()

    import aiomysql

    conn_str = await get_connection_string()
    db_params = AIOMySQLSaver.parse_conn_string(conn_str)

    try:
        conn = await aiomysql.connect(**db_params, autocommit=True)
        return AIOMySQLSaver(conn=conn)
    except Exception as exc:
        if allow_memory_fallback:
            logger.warning("MySQL checkpointer unavailable, falling back to memory saver: %s", exc)
            return MemorySaver()
        raise RuntimeError(f"Failed to initialize MySQL checkpointer: {exc}") from exc


if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(build_graph())
        print("Graph built successfully.")
    except Exception as exc:
        print(f"Graph build failed: {exc}")
