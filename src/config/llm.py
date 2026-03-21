import os
from typing import Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

DEFAULT_OPENAI_PROXY_BASE_URL = "https://api.openai-proxy.org/v1"
DEFAULT_ANTHROPIC_PROXY_BASE_URL = "https://api.openai-proxy.org/anthropic/v1"


def _get_first_env(*keys: str) -> Optional[str]:
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    return None


def _normalize_base_url(base_url: Optional[str], fallback: str) -> str:
    value = (base_url or fallback).rstrip("/")
    if value.endswith("/v1"):
        return value
    return f"{value}/v1"


def _require_api_key(*keys: str) -> str:
    api_key = _get_first_env(*keys)
    if api_key:
        return api_key
    raise RuntimeError(
        f"Missing LLM API key. Set one of: {', '.join(keys)}."
    )


def get_gpt_model(model: Optional[str] = None, streaming: bool = False):
    resolved_model = model or _get_first_env("OPENAI_COMPAT_MODEL") or "gpt-4o-mini"
    api_key = _require_api_key("OPENAI_COMPAT_API_KEY", "OPENAI_PROXY_API_KEY", "close")
    base_url = _normalize_base_url(
        _get_first_env("OPENAI_COMPAT_BASE_URL", "OPENAI_PROXY_BASE_URL"),
        DEFAULT_OPENAI_PROXY_BASE_URL,
    )
    return ChatOpenAI(
        model=resolved_model,
        api_key=api_key,
        base_url=base_url,
        streaming=streaming,
    )


def get_claude_model(model: str = "claude-haiku-4-5", streaming: bool = False):
    api_key = _require_api_key("OPENAI_COMPAT_API_KEY", "OPENAI_PROXY_API_KEY", "close")
    base_url = _normalize_base_url(
        _get_first_env("ANTHROPIC_PROXY_BASE_URL"),
        DEFAULT_ANTHROPIC_PROXY_BASE_URL,
    )
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=streaming,
    )


def mt_llm(model: str = "gpt-4.1", streaming: bool = False):
    api_key = _require_api_key("MT_OPENAI_API_KEY", "mt")
    base_url = (_get_first_env("MT_OPENAI_BASE_URL") or "https://aigc.sankuai.com/v1/openai/native").rstrip("/")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=streaming,
    )
