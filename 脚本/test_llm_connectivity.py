import argparse
import asyncio
import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.config.llm import get_claude_model, get_gpt_model, mt_llm


def build_model(target: str):
    if target == "gpt4mini":
        return get_gpt_model("gpt-4o-mini")
    if target == "claude":
        return get_claude_model()
    if target == "mt":
        return get_gpt_model(streaming=False)
    raise ValueError(f"Unsupported target: {target}")


async def main() -> None:
    llm = build_model("claude")
    response = await llm.ainvoke([HumanMessage(content="你好")])

    print(
        json.dumps(
            {
                "response": response.content,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
