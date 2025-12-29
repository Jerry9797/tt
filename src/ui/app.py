import streamlit as st
import uuid
import json
import sys
import asyncio
from pathlib import Path

# 将项目根目录添加到 sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.fastapi.app import chat, ChatRequest
from src.nodes.build_graph import build_graph
from src.utils.time_travel_utils import (
    get_state_history,
    format_checkpoint_info,
    get_checkpoint_details,
    rollback_to_checkpoint,
    update_and_continue, get_all_thread_ids
)

st.set_page_config(page_title="ces", layout="wide")

st.title("🤖 ces")

# 初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = f"session_{uuid.uuid4().hex[:8]}"

if "waiting_for_clarification" not in st.session_state:
    st.session_state.waiting_for_clarification = False

# 注意：我们不再在启动时全局初始化 graph
# 因为 build_graph 现在强制使用异步 MySQL Saver，需要事件循环
# if "graph" not in st.session_state:
#     st.session_state.graph = build_graph()

if "selected_checkpoint_idx" not in st.session_state:
    st.session_state.selected_checkpoint_idx = None

# 初始化 selected_thread_id
if "selected_thread_id" not in st.session_state:
    st.session_state.selected_thread_id = "default_thread"

# Sidebar 显示当前状态
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Thread ID 管理
    thread_id = st.text_input("Thread ID", value=st.session_state.selected_thread_id)
    if thread_id != st.session_state.selected_thread_id:
        st.session_state.selected_thread_id = thread_id
        st.session_state.messages = [] # 切换 thread 时清空显示的消息
        st.rerun()

    st.header("Debug Info")
    st.text(f"Thread ID: {st.session_state.thread_id}")
    st.checkbox("Waiting for Clarification", value=st.session_state.waiting_for_clarification, disabled=True)
    if st.button("New Session"):
        st.session_state.messages = []
        st.session_state.thread_id = f"session_{uuid.uuid4().hex[:8]}"
        st.session_state.waiting_for_clarification = False
        st.session_state.selected_checkpoint_idx = None
        st.rerun()
    
    st.divider()
    
    # Time Travel Section
    st.header("⏰ Time Travel")
    
    # 历史会话选择器
    st.subheader("📂 Session History")
    
    # 获取所有 thread_id (需要异步获取)
    # ⭐ 动态构建 Graph
    # import asyncio # 已经导入
    # from src.nodes.build_graph import build_graph # 已经导入
    
    async def fetch_thread_ids():
        graph = None
        try:
            # 仅获取历史记录不需要 MCP 工具，跳过初始化以提高速度并避免 async 上下文错误
            graph = await build_graph(init_mcp=False)
            # 获取所有 thread_ids (注意: get_all_thread_ids 也需要适配异步或能够处理异步 checkpointer)
            # 这里的 get_all_thread_ids 在 time_travel_utils.py 中，稍后需要检查是否支持异步 checkpointer
            return await get_all_thread_ids(graph)
        finally:
            # 显式关闭数据库连接，防止 Event loop is closed 错误
            if graph and hasattr(graph.checkpointer, 'conn'):
                graph.checkpointer.conn.close()
            
    try:
        all_thread_ids = asyncio.run(fetch_thread_ids())
    except Exception as e:
        print(f"Async fetch failed: {e}")
        all_thread_ids = []

    if not all_thread_ids:
        st.info("No historical sessions found.")
        # 如果没有历史会话，将当前会话ID作为唯一选项
        all_thread_ids = [st.session_state.thread_id]
        selected_thread_id = st.session_state.thread_id
    else:
        # 确保当前 thread_id 在列表中
        if st.session_state.thread_id not in all_thread_ids:
            all_thread_ids.insert(0, st.session_state.thread_id)
        
        # 创建显示选项（显示当前会话标记）
        def format_thread_option(tid):
            if tid == st.session_state.thread_id:
                return f"🟢 {tid} (Current)"
            return f"   {tid}"
        
        selected_thread_id = st.selectbox(
            "Select Session",
            options=all_thread_ids,
            format_func=format_thread_option,
            index=all_thread_ids.index(st.session_state.thread_id) if st.session_state.thread_id in all_thread_ids else 0,
            key="thread_selector",
            help="选择要查看的历史会话"
        )
        
        # 如果选择的不是当前会话，显示提示
        if selected_thread_id != st.session_state.thread_id:
            st.info(f"📜 Viewing history from: `{selected_thread_id}`")
            if st.button("Switch to this session", help="切换到此会话并继续对话"):
                st.session_state.thread_id = selected_thread_id
                st.session_state.messages = []  # 清空当前消息
                st.rerun()
    
    st.divider()
    st.divider()
    st.subheader("🕐 Checkpoints")
    
    # 获取选中 thread 的历史状态（使用 selected_thread_id 而不是当前 thread_id）
    # ⭐ 需要在异步上下文中重建 graph 以连接 MySQL
    import asyncio
    from src.nodes.build_graph import build_graph
    
    async def fetch_history_from_mysql():
        graph = None
        try:
            # 在这里重建 graph，因为它会检测到运行的 loop 并使用 MySQL
            # 获取 Checkpoints 也不需要 MCP
            graph = await build_graph(init_mcp=False)
            return await get_state_history(graph, selected_thread_id)
        finally:
            if graph and hasattr(graph.checkpointer, 'conn'):
                graph.checkpointer.conn.close()
        
    try:
        history = asyncio.run(fetch_history_from_mysql())
    except Exception as e:
        print(f"获取历史失败: {e}")
        history = []
    
    if not history:
        st.info("No checkpoints available yet. Start a conversation to create checkpoints.")
    else:
        st.success(f"Found {len(history)} checkpoints")
        
        # 显示 checkpoint 列表
        checkpoint_options = [format_checkpoint_info(cp, i) for i, cp in enumerate(history)]
        
        selected = st.selectbox(
            "Select Checkpoint",
            options=range(len(history)),
            format_func=lambda i: checkpoint_options[i],
            key="checkpoint_selector"
        )
        
        if selected is not None:
            st.session_state.selected_checkpoint_idx = selected
            selected_checkpoint = history[selected]
            
            # 显示详细信息
            with st.expander("📋 Checkpoint Details", expanded=False):
                st.json(selected_checkpoint.get("values", {}))
            
            # 操作按钮
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("🔄 Rollback", help="从此 checkpoint 继续执行"):
                    try:
                        checkpoint_id = selected_checkpoint["checkpoint_id"]
                        with st.spinner("Rolling back..."):
                            result = rollback_to_checkpoint(
                                st.session_state.graph,
                                st.session_state.thread_id,
                                checkpoint_id,
                                inputs=None
                            )
                        st.success("Rollback successful!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Rollback failed: {e}")
            
            with col2:
                if st.button("✏️ Edit State", help="修改状态并继续"):
                    st.session_state.show_edit_form = True
            
            # 编辑表单
            if st.session_state.get("show_edit_form", False):
                with st.form("edit_state_form"):
                    st.subheader("Edit State")
                    
                    # 获取当前状态
                    current_values = selected_checkpoint.get("values", {})
                    
                    # 为主要字段提供编辑框
                    edited_query = st.text_input(
                        "Query",
                        value=current_values.get("query", ""),
                        help="修改用户查询"
                    )
                    
                    # 选择从哪个节点继续
                    as_node = st.selectbox(
                        "Continue from node",
                        options=["query_rewrite_node", "faq_retrieve_node", "planning_node", "plan_executor_node"],
                        help="选择从哪个节点继续执行"
                    )
                    
                    submitted = st.form_submit_button("Apply & Continue")
                    
                    if submitted:
                        try:
                            updates = {"query": edited_query}
                            checkpoint_id = selected_checkpoint["checkpoint_id"]
                            
                            with st.spinner("Updating state and continuing..."):
                                # 定义异步执行函数
                                async def run_update():
                                    graph = None
                                    try:
                                        # 但对于 Streamlit 这种无长驻 loop 的环境，这是确保连接有效的最简单方法
                                        from src.nodes.build_graph import build_graph
                                        graph = await build_graph()
                                        
                                        return await update_and_continue(
                                            graph,
                                            st.session_state.thread_id,
                                            checkpoint_id,
                                            updates,
                                            as_node=as_node
                                        )
                                    finally:
                                        if graph and hasattr(graph.checkpointer, 'conn'):
                                            graph.checkpointer.conn.close()

                                result = asyncio.run(run_update())
                            
                            st.success("State updated and execution continued!")
                            st.session_state.show_edit_form = False
                            st.rerun()
                        except Exception as e:
                            st.error(f"Update failed: {e}")

# 渲染历史消息
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 处理用户输入
if prompt := st.chat_input("Input your query..."):
    # 1. 显示用户输入
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. 调用 API 的 chat 方法
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Thinking...")
        
        try:
            # 构造请求对象
            request_data = {
                "thread_id": st.session_state.thread_id,
                "history": [] # 历史消息通常在第一次请求时可选，Graph 内部有持久化
            }
            
            if st.session_state.waiting_for_clarification:
                request_data["resume_input"] = prompt
            else:
                request_data["query"] = prompt
                # 仅在第一次或特殊情况下传递前端历史，这里保持简单
                frontend_history = []
                for msg in st.session_state.messages[:-1]:
                    role = "user" if msg["role"] == "user" else "assistant"
                    frontend_history.append({"role": role, "content": msg["content"]})
                request_data["history"] = frontend_history

            chat_request = ChatRequest(**request_data)
            
            # 直接调用 API 内部的 chat 函数 (async)
            # 使用 asyncio.run 在同步环境中运行异步函数
            
            async def run_chat_with_cleanup():
                try:
                    return await chat(chat_request)
                finally:
                    # 确保 MCP 资源释放，防止 loop closed error
                    # chat 内部可能初始化了 MCP (如果 build_graph init_mcp=True)
                    from src.mcp.mcp_manager import cleanup_mcp_manager
                    await cleanup_mcp_manager()
            
            result = asyncio.run(run_chat_with_cleanup())
            
            # 3. 处理响应
            if result.status == "need_clarification":
                st.session_state.waiting_for_clarification = True
                reply_text = f"**[需要澄清]** {result.response}"
            else:
                st.session_state.waiting_for_clarification = False
                reply_parts = []
                
                if result.response:
                    reply_parts.append(f"{result.response}")
                
                if result.faq_response:
                    reply_parts.append(f"**FAQ Answer:**\n{result.faq_response}")
                
                if result.plan:
                    plan_str = "\n".join([f"- {step}" for step in result.plan])
                    reply_parts.append(f"**Plan:**\n{plan_str}")
                
                if result.intent:
                    reply_parts.append(f"**Intent:** `{result.intent}`")
                
                if not reply_parts:
                    reply_text = f"Result: {result.json()}"
                else:
                    reply_text = "\n\n---\n\n".join(reply_parts)
            
            message_placeholder.markdown(reply_text)
            st.session_state.messages.append({"role": "assistant", "content": reply_text})
            
        except Exception as e:
            import traceback
            error_msg = f"Error: {str(e)}\n\n```\n{traceback.format_exc()}\n```"
            message_placeholder.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
