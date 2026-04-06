import os
import redis
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        pool = redis.ConnectionPool(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=int(os.getenv("REDIS_DB", 0)),
            password=os.getenv("REDIS_PASSWORD", None),
            decode_responses=True,
        )
        _client = redis.Redis(connection_pool=pool)
    return _client