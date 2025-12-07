from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from config.llm import TongyiEmbedding

client = QdrantClient(
    host="23.91.97.241",   # 推荐用 host + port 而非 url（更清晰）
    port=6333,
    # api_key="your_api_key_here"
)

collection_name = "dz_channel_faq"
vector_size = 1536  # 确保与 TongyiEmbedding 输出维度一致

# ✅ 安全创建：先检查是否已存在，避免重复创建报错
if not client.collection_exists(collection_name):
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
    )
    print(f"✅ 集合 '{collection_name}' 创建成功！")
else:
    print(f"⚠️ 集合 '{collection_name}' 已存在，跳过创建。")

# 示例 FAQ 数据
faqs = [
    {"question": "如何重置密码？", "answer": "请访问设置页面..."},
    {"question": "支持哪些支付方式？", "answer": "支持支付宝、微信..."}
]

eb = TongyiEmbedding()
points = []
for i, faq in enumerate(faqs):
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

if __name__ == '__main__':
    # ✅ 执行 upsert
    client.upsert(collection_name=collection_name, points=points)
    print(f"✅ 成功插入 {len(points)} 条 FAQ 数据到 '{collection_name}'")