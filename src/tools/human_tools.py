from typing import Dict

from langchain_core.tools import tool


@tool
def ask_human(question: str) -> Dict[str, str]:
    """
    当执行当前步骤需要用户补充信息时调用此工具。

    这个工具不会真正访问外部系统，它只用于显式声明：
    当前节点需要暂停，并向用户提出一个澄清问题。

    Args:
        question: 需要向用户提出的问题
    """
    return {"question": question}
