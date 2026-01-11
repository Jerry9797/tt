from datetime import datetime

from langchain_core.tools import tool


@tool
def get_current_time() -> str:
    """
    获取当前时间（用于时间相关查询）

    Returns:
        当前时间字符串，格式：2024-12-24 12:30:00
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")