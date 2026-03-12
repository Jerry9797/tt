import os

from langchain_community.embeddings import DashScopeEmbeddings,zhipuai
from dotenv import load_dotenv

load_dotenv()


def TongyiEmbedding()->DashScopeEmbeddings:
    api_key = os.environ.get("tongyi") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("Missing DashScope API key. Set `tongyi` or `DASHSCOPE_API_KEY` in the environment.")
    return DashScopeEmbeddings(dashscope_api_key=api_key,
                           model="text-embedding-v1")

from langchain_qdrant import QdrantVectorStore
def QdrantVecStore(eb:DashScopeEmbeddings,collection_name:str):
    return QdrantVectorStore.from_existing_collection(embedding=eb, url="http://23.91.97.241:6333", collection_name=collection_name)
