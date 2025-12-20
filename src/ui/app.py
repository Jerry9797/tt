import streamlit as st
import requests
import uuid
import json

# 配置 API 地址
API_URL = "http://localhost:8000/chat"

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

    # 2. 准备请求 Payload
    payload = {
        "history": st.session_state.messages[:-1], # 传递除了当前这条之外的历史
        "thread_id": st.session_state.thread_id
    }

    if st.session_state.waiting_for_clarification:
        # 如果处于等待澄清状态，发送 resume_input
        payload["resume_input"] = prompt
        # Query 字段在模型里是必填的，虽然 resume 时可能不用，但为了过校验随便填一个或者填prompt
        payload["query"] = prompt 
    else:
        # 正常请求
        payload["query"] = prompt

    # 3. 发送请求
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Thinking...")
        
        try:
            response = requests.post(API_URL, json=payload)
            if response.status_code == 200:
                data = response.json()
                
                # 更新状态标志
                if data.get("status") == "need_clarification":
                    st.session_state.waiting_for_clarification = True
                    reply_text = f"**[需要澄清]** {data.get('response')}"
                else:
                    st.session_state.waiting_for_clarification = False
                    # 组合展示结果
                    reply_parts = []
                    if data.get("response"):
                        # 如果有中间响应（比如澄清后的问题回显，或者其他）
                        reply_parts.append(f"{data.get('response')}")
                    
                    if data.get("faq_response"):
                        reply_parts.append(f"**FAQ Answer:**\n{data.get('faq_response')}")
                    
                    if data.get("plan"):
                        plan_str = "\n".join([f"- {step}" for step in data.get("plan")])
                        reply_parts.append(f"**Plan:**\n{plan_str}")
                    
                    if data.get("intent"):
                         reply_parts.append(f"**Intent:** `{data.get('intent')}`")

                    # 如果没有内容，兜底
                    if not reply_parts:
                        reply_text = f"Response: {json.dumps(data, ensure_ascii=False, indent=2)}"
                    else:
                        reply_text = "\n\n---\n\n".join(reply_parts)

                message_placeholder.markdown(reply_text)
                st.session_state.messages.append({"role": "assistant", "content": reply_text})
                
            else:
                error_msg = f"Error: {response.status_code} - {response.text}"
                message_placeholder.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

        except Exception as e:
            error_msg = f"Connection failed: {str(e)}"
            message_placeholder.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
