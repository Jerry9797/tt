import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from langchain_community.chat_models import ChatTongyi, ChatZhipuAI

load_dotenv()


def get_gpt_model(model:str = "gpt-4o-mini", streaming: bool = False):
    return ChatOpenAI(
        model=model,
        api_key=os.environ.get("close"),
        base_url="https://api.openai-proxy.org/v1",
        streaming=streaming
    )

def get_claude_model(model:str = "claude-haiku-4-5", streaming: bool = False):
    return ChatOpenAI(
        model=model,
        api_key=os.environ.get("close"),
        base_url="https://api.openai-proxy.org/anthropic",
        streaming=streaming
    )

def mt_llm(model:str = "gpt-4.1", streaming: bool = False):
    return ChatOpenAI(
        model=model,
        api_key=os.environ.get("mt"),
        base_url="https://aigc.sankuai.com/v1/openai/native",
        # streaming=streaming,
    )
