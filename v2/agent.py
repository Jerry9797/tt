"""
v2 诊断 Agent — 基于 Claude Code SDK
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from claude_code_sdk import ClaudeCodeOptions, query
from claude_code_sdk.types import (
    AssistantMessage, ResultMessage, SystemMessage,
    TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock,
)
from opentelemetry import trace
from opentelemetry.trace import StatusCode

from telemetry import init_telemetry, get_tracer

# Load .env from v2/ directory (API keys, model config)
load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger(__name__)
SKILLS_DIR = Path(__file__).parent / "skills"


def build_system_prompt() -> str:
    parts = [
        "你是美团后端技术支持诊断助手。",
        "根据用户的问题，选择最匹配的 SOP（Standard Operating Procedure）并给出诊断。",
        "如果当前信息不足或某个 SOP 依赖外部工具数据，而本次运行未提供相关工具，请明确指出缺失信息，不要编造结论。",
        "最终给出结构化诊断报告：根因、证据、建议操作。",
        "",
        "=" * 60,
        "以下是所有可用的 SOP（按场景分类）：",
        "=" * 60,
        "",
    ]
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            content = skill_file.read_text(encoding="utf-8")
            parts.append(f"# SOP: {skill_dir.name}\n\n{content}\n")
            parts.append("-" * 40 + "\n")
    return "\n".join(parts)


SYSTEM_PROMPT = build_system_prompt()


def build_sdk_env() -> dict[str, str]:
    """Build env vars for the Claude Code subprocess (OTEL config for SDK side)."""
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": os.getenv("CLAUDE_CODE_ENABLE_TELEMETRY", "1"),
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": os.getenv("CLAUDE_CODE_ENHANCED_TELEMETRY_BETA", "1"),
        "OTEL_LOGS_EXPORTER": os.getenv("OTEL_LOGS_EXPORTER", "otlp"),
        "OTEL_METRICS_EXPORTER": os.getenv("OTEL_METRICS_EXPORTER", "otlp"),
        "OTEL_TRACES_EXPORTER": os.getenv("OTEL_TRACES_EXPORTER", "otlp"),
        "OTEL_EXPORTER_OTLP_PROTOCOL": os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf"),
        "OTEL_EXPORTER_OTLP_ENDPOINT": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318"),
        "OTEL_LOG_USER_PROMPTS": os.getenv("OTEL_LOG_USER_PROMPTS", "1"),
        "OTEL_SERVICE_NAME": os.getenv("OTEL_SERVICE_NAME", "tt-v2-agent"),
        "OTEL_RESOURCE_ATTRIBUTES": os.getenv(
            "OTEL_RESOURCE_ATTRIBUTES",
            "deployment.environment=dev,service.version=v2",
        ),
        "OTEL_METRIC_EXPORT_INTERVAL": os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "1000"),
        "OTEL_LOGS_EXPORT_INTERVAL": os.getenv("OTEL_LOGS_EXPORT_INTERVAL", "1000"),
        "OTEL_TRACES_EXPORT_INTERVAL": os.getenv("OTEL_TRACES_EXPORT_INTERVAL", "1000"),
    }


def _build_settings_json() -> str:
    """Build the settings JSON with env-sourced API keys."""
    return json.dumps({
        "env": {
            "ANTHROPIC_BASE_URL": os.getenv("ANTHROPIC_BASE_URL", ""),
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
            "ANTHROPIC_DEFAULT_OPUS_MODEL": os.getenv("ANTHROPIC_DEFAULT_OPUS_MODEL", "qwen3.6-plus"),
            "ANTHROPIC_DEFAULT_SONNET_MODEL": os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "qwen3.6-plus"),
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": os.getenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", "qwen3-coder-next"),
        }
    })


async def run_query(user_query: str) -> str:
    """执行单轮诊断查询，返回助手回复文本。"""
    tracer = get_tracer()

    with tracer.start_as_current_span(
        "run_query",
        attributes={"query.text": user_query[:200]},
    ) as span:
        options = ClaudeCodeOptions(
            system_prompt=SYSTEM_PROMPT,
            permission_mode="bypassPermissions",
            max_turns=5,
            allowed_tools=["Read", "Edit", "Bash", "Grep", "Glob"],
            disallowed_tools=["Agent", "AskUserQuestion", "TodoWrite", "TodoRead"],
            env=build_sdk_env(),
            settings=_build_settings_json(),
        )

        response_parts: list[str] = []
        tool_calls: list[str] = []

        try:
            async for message in query(prompt=user_query, options=options):
                if isinstance(message, AssistantMessage):
                    _handle_assistant_message(message, response_parts, tool_calls, span)
                elif isinstance(message, ResultMessage):
                    _handle_result_message(message, response_parts, span)
                elif isinstance(message, SystemMessage):
                    logger.debug("SystemMessage subtype=%s", message.subtype)
                else:
                    logger.debug("Unknown message type: %s", type(message).__name__)

        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            logger.error("run_query failed: %s", exc, exc_info=True)
            raise

        if tool_calls:
            span.set_attribute("query.tool_calls", tool_calls)

        return "\n".join(response_parts)


def _handle_assistant_message(
    message: AssistantMessage,
    response_parts: list[str],
    tool_calls: list[str],
    span: trace.Span,
) -> None:
    """Process an AssistantMessage: extract text, log tool use."""
    span.set_attribute("assistant.model", message.model)
    for block in message.content:
        if isinstance(block, TextBlock):
            response_parts.append(block.text)
            print(block.text, end="", flush=True)
            span.add_event("assistant.text", {"text": block.text})
        elif isinstance(block, ToolUseBlock):
            tool_calls.append(block.name)
            logger.info("Tool call: %s(%s)", block.name, list(block.input.keys()))
            span.add_event("tool.use", {
                "tool.name": block.name,
                "tool.use_id": block.id,
                "tool.input": json.dumps(block.input, ensure_ascii=False)[:500],
            })
        elif isinstance(block, ToolResultBlock):
            content_str = block.content if isinstance(block.content, str) else json.dumps(block.content, ensure_ascii=False)
            span.add_event("tool.result", {
                "tool.use_id": block.tool_use_id,
                "tool.is_error": bool(block.is_error),
                "tool.output": (content_str or "")[:500],
            })
            if block.is_error:
                logger.warning("Tool %s returned error", block.tool_use_id)
        elif isinstance(block, ThinkingBlock):
            span.add_event("assistant.thinking", {"thinking": block.thinking[:300]})
            logger.debug("Thinking: %s...", block.thinking[:100])


def _handle_result_message(
    message: ResultMessage,
    response_parts: list[str],
    span: trace.Span,
) -> None:
    """Process ResultMessage: record all metadata as span attributes."""
    if message.result:
        response_parts.append(message.result)

    span.set_attribute("result.duration_ms", message.duration_ms)
    span.set_attribute("result.duration_api_ms", message.duration_api_ms)
    span.set_attribute("result.is_error", message.is_error)
    span.set_attribute("result.num_turns", message.num_turns)
    span.set_attribute("result.session_id", message.session_id)

    if message.total_cost_usd is not None:
        span.set_attribute("result.total_cost_usd", message.total_cost_usd)

    if message.usage:
        for key, value in message.usage.items():
            if isinstance(value, (int, float)):
                span.set_attribute(f"result.usage.{key}", value)

    if message.is_error:
        span.set_status(StatusCode.ERROR, "SDK returned is_error=True")
        logger.error("Query ended with error. session_id=%s", message.session_id)
    else:
        span.set_status(StatusCode.OK)

    logger.info(
        "Query complete: duration=%dms, api_duration=%dms, turns=%d, cost=$%.4f, session=%s",
        message.duration_ms,
        message.duration_api_ms,
        message.num_turns,
        message.total_cost_usd or 0,
        message.session_id,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    provider = init_telemetry()

    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "商户1002在美团列表中不展示"
    print(f"\n查询：{user_input}\n{'=' * 50}")

    try:
        asyncio.run(run_query(user_input))
    finally:
        provider.shutdown()
