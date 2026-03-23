from __future__ import annotations

import json
from argparse import ArgumentParser
from datetime import datetime


def get_current_hour_range(round_to_minute: bool = True) -> dict[str, int]:
    """返回当前小时段的毫秒时间戳。"""
    now = datetime.now()
    start_time = now.replace(minute=0, second=0, microsecond=0)

    if round_to_minute:
        end_time = now.replace(second=0, microsecond=0)
    else:
        end_time = now.replace(microsecond=0)

    return {
        "startTime": int(start_time.timestamp() * 1000),
        "endTime": int(end_time.timestamp() * 1000),
    }


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="生成当前小时段的毫秒时间戳")
    parser.add_argument(
        "--exact-second",
        action="store_true",
        help="endTime 保留到当前秒；默认向下取整到当前分钟。",
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    result = get_current_hour_range(round_to_minute=not args.exact_second)
    print(json.dumps(result, ensure_ascii=False, indent=2))
