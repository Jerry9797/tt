from typing import List
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from config.llm import TongyiEmbedding
from src.graph_state import AgentState
from qdrant_client.http import models


client = QdrantClient(host="23.91.97.241", port=6333)
eb = TongyiEmbedding()

def qdrant_select(query: str,score_threshold : float = 0.75, collection_name: str = "dz_channel_faq"):
    query_vector = eb.embed_query(query)

    # 关键词检索，假设 有 { "keywords": ["曝光", "门店", "流量"] }
    # filter = models.Filter(
    #     must=[
    #         models.FieldCondition(
    #             key="keywords",
    #             match=models.MatchValue(value="曝光")
    #         )
    #     ]
    # )

    results = client.query_points(
        collection_name=collection_name,
        query= query_vector,
        limit=3,
        # filter=filter,
        score_threshold=score_threshold  # 可选：过滤低分结果
    )
    return results

vector_size = 1536
def qdrant_insert_faq(faq_list: List[dict], collection_name : str = "dz_channel_faq"):
    points = []
    for i, faq in enumerate(faq_list):
        vector = eb.embed_query(faq["question"])
        # ✅ 安全检查：确保 embedding 维度正确
        assert len(vector) == vector_size, f"Embedding 维度不匹配！期望 {vector_size}，实际 {len(vector)}"
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

