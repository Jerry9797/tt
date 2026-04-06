import os

from langchain_community.embeddings import DashScopeEmbeddings
from dotenv import load_dotenv
from langchain_qdrant import QdrantVectorStore

from src.config.qdrant import get_qdrant_url

load_dotenv()


def TongyiEmbedding()->DashScopeEmbeddings:
    api_key = os.environ.get("tongyi") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("Missing DashScope API key. Set `tongyi` or `DASHSCOPE_API_KEY` in the environment.")
    return DashScopeEmbeddings(dashscope_api_key=api_key,
                           model="text-embedding-v1")

def QdrantVecStore(eb:DashScopeEmbeddings,collection_name:str):
    return QdrantVectorStore.from_existing_collection(
        embedding=eb,
        url=get_qdrant_url(),
        collection_name=collection_name,
    )
