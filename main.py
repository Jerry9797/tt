import asyncio
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
# 确保你的路径正确
from src.config.llm import get_claude_model, get_gpt_model

# 1. 修正 Prompt 定义
# from_messages 必须接收一个列表 []
# 建议加上 ("human", "{input}") 这样才能接收 ainvoke 传进来的内容
response_prompt = ChatPromptTemplate.from_messages([
    SystemMessage(content="你是一个专业的智能诊断助手。"),
    ("human", "{user_input}")
])


async def main():
    # 2. 获取模型（请确认 gpt-4.1 是否是你们网关定义的特殊名称，否则建议用 gpt-4o）
    model = get_claude_model(model="claude-haiku-4-5", streaming=True)

    # 3. 组合 Chain
    chain = response_prompt | model

    # 4. 修正 ainvoke 传参
    # 必须传入字典，Key 要对应 Prompt 里的占位符变量名
    resp = await chain.ainvoke({"user_input": "你好"})

    # resp 是一个 BaseMessage 对象，打印其 content
    print(resp.content)


if __name__ == '__main__':
    asyncio.run(main())