from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from dotenv import load_dotenv

from src.config.eb import TongyiEmbedding
from src.config.qdrant import get_qdrant_client_kwargs
from src.constants import EMBEDDING_VECTOR_SIZE

load_dotenv()

_client = None
_eb = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(**get_qdrant_client_kwargs())
    return _client


def _get_eb():
    global _eb
    if _eb is None:
        _eb = TongyiEmbedding()
    return _eb

def qdrant_select(query: str, score_threshold: float = 0.75, collection_name: str = "dz_channel_faq"):
    query_vector = _get_eb().embed_query(query)

    results = _get_client().query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=3,
        score_threshold=score_threshold,
    )
    return results

# 存储faq
def qdrant_insert_faq(faq_list: List[dict], collection_name: str = "dz_channel_faq"):
    points = []
    eb = _get_eb()
    client = _get_client()
    for i, faq in enumerate(faq_list):
        vector = eb.embed_query(faq["question"])
        # ✅ 安全检查：确保 embedding 维度正确
        assert len(vector) == EMBEDDING_VECTOR_SIZE, f"Embedding 维度不匹配！期望 {EMBEDDING_VECTOR_SIZE}，实际 {len(vector)}"
        points.append(
            PointStruct(
                id=i,
                vector=vector,
                payload={
                    "question": faq["question"],
                    "answer": faq["answer"]
                }
            )
        )
    if points:
        client.upsert(collection_name=collection_name, points=points)
