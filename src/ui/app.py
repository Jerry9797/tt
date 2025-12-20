import streamlit as st
import uuid
import json
import sys
import asyncio
from pathlib import Path

# 将项目根目录添加到 sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.api.app import chat, ChatRequest

st.set_page_config(page_title="TT Assistant Debugger", layout="wide")

st.title("🤖 TT Assistant Debugger")

# 初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

if "thread_id" not in st.session_state:
    st.session_state.thread_id = f"session_{uuid.uuid4().hex[:8]}"

if "waiting_for_clarification" not in st.session_state:
    st.session_state.waiting_for_clarification = False

# Sidebar 显示当前状态
with st.sidebar:
    st.header("Debug Info")
    st.text(f"Thread ID: {st.session_state.thread_id}")
    st.checkbox("Waiting for Clarification", value=st.session_state.waiting_for_clarification, disabled=True)
    if st.button("New Session"):
        st.session_state.messages = []
        st.session_state.thread_id = f"session_{uuid.uuid4().hex[:8]}"
        st.session_state.waiting_for_clarification = False
        st.rerun()

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
            result = asyncio.run(chat(chat_request))
            
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
