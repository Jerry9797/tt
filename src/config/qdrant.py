import os

from dotenv import load_dotenv

load_dotenv()

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_HTTPS = os.getenv("QDRANT_HTTPS", "false").lower() == "true"


def get_qdrant_client_kwargs() -> dict:
    kwargs = {
        "host": QDRANT_HOST,
        "port": QDRANT_PORT,
        "https": QDRANT_HTTPS,
    }
    if QDRANT_API_KEY:
        kwargs["api_key"] = QDRANT_API_KEY
    return kwargs


def get_qdrant_url() -> str:
    scheme = "https" if QDRANT_HTTPS else "http"
    return f"{scheme}://{QDRANT_HOST}:{QDRANT_PORT}"
