import os

import warnings
from openai import OpenAI
from dotenv import load_dotenv
from langchain_community.chat_models import ChatZhipuAI
from langchain_community.embeddings import DashScopeEmbeddings,zhipuai

from langchain_openai import ChatOpenAI

load_dotenv()

def Zhipuai():
    return ChatZhipuAI(
        model="glm-4-flash", # 免费
        api_key=os.environ.get("zhipu"),
        base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        temperature=0.5,
    )

def qwenmax(callbacks=[]):
    return ChatOpenAI(
        model="qwen-max",
        api_key=os.environ.get("tongyi"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        callbacks=callbacks
    )

def qwenplus():
    return ChatOpenAI(
        model="qwen-plus",
        api_key=os.environ.get("tongyi"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

def qwencoder():
    return ChatOpenAI(
        model="qwen3-coder-plus",
        api_key=os.environ.get("tongyi"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

def tongyi_intent():
    return ChatOpenAI(
        model="tongyi-intent-detect-v3",
        api_key=os.environ.get("tongyi"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )


def DeepseekAI():
    return ChatOpenAI(
        model="deepseek-coder",
        api_key=os.environ.get("deepseek"),
        base_url="https://api.deepseek.com/v1"
    )


def get_gpt_model():
    close = os.environ.get("close")
    return ChatOpenAI(
        model='gpt-5',
        api_key=close,
        base_url="https://api.openai-proxy.org/v1"
    )

def get_claude_model():
    close = os.environ.get("close")
    return ChatOpenAI(
        model='claude-sonnet-4-20250514',
        api_key=close,
        base_url="https://api.openai-proxy.org/anthropic"
    )

# 通义千问的embedding
def TongyiEmbedding()->DashScopeEmbeddings:
    api_key=os.environ.get("tongyi")
    return DashScopeEmbeddings(dashscope_api_key=api_key,
                           model="text-embedding-v1")

from langchain_qdrant import QdrantVectorStore
def QdrantVecStore(eb:DashScopeEmbeddings,collection_name:str):
    return  QdrantVectorStore.\
        from_existing_collection(embedding=eb,
         url="http://23.91.97.241:6333",
          collection_name=collection_name)


def mt_llm(model:str = "qwen-max-latest"):
    return ChatOpenAI(
        model=model,
        api_key=os.environ.get("mt"),
        base_url="https://aigc.sankuai.com/v1/openai/native"
    )