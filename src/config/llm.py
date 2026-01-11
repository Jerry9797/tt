import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from langchain_community.chat_models import ChatTongyi, ChatZhipuAI

load_dotenv()


q_max = ChatTongyi(
    model="qwen-max",
    api_key=os.environ.get("tongyi"),
    streaming=False,
)

q_plus = ChatTongyi(
    model="qwen-plus",
    api_key=os.environ.get("tongyi"),
    streaming=False,
)

q_coder_plus = ChatTongyi(
    model="qwen3-coder-plus",
    api_key=os.environ.get("tongyi"),
    streaming=False,
)

q_intent = ChatTongyi(
    model="tongyi-intent-detect-v3",
    api_key=os.environ.get("tongyi"),
)

zhipu_flash = ChatZhipuAI(
        model="glm-4-flash", # 免费
        api_key=os.environ.get("zhipu"),
        temperature=0.5,
)


deepseek_coder = ChatOpenAI(
        model="deepseek-coder",
        api_key=os.environ.get("deepseek"),
        base_url="https://api.deepseek.com/v1"
)

glm_4_7 = ChatZhipuAI(
    model="glm-4.7",
    api_key=os.environ.get("zhipu"),
    streaming=False,
    temperature=0.5,
)


def get_gpt_model(model:str = "gpt-4o-mini"):
    return ChatOpenAI(
        model=model,
        api_key=os.environ.get("close"),
        base_url="https://api.openai-proxy.org/v1"
    )

def get_claude_model():
    return ChatOpenAI(
        model='claude-sonnet-4-20250514',
        api_key=os.environ.get("close"),
        base_url="https://api.openai-proxy.org/anthropic"
    )

def mt_llm(model:str = "qwen-max-latest"):
    return ChatOpenAI(
        model=model,
        api_key=os.environ.get("mt"),
        base_url="https://aigc.sankuai.com/v1/openai/native"
    )