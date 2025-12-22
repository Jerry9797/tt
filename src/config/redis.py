import os
import redis
from dotenv import load_dotenv

load_dotenv()

def get_redis_client():
    pool = redis.ConnectionPool(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=int(os.getenv("REDIS_DB", 0)),
        password=os.getenv("REDIS_PASSWORD", None),
        decode_responses=True
    )
    return redis.Redis(connection_pool=pool)

client = get_redis_client()