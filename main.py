import tiktoken

from src.config.sop_loader import get_sop_loader
from src.prompt.prompt_loader import get_prompt


def count_openai_tokens(text: str, model: str = "gpt-4.1"):
    try:
        # 自动根据模型名加载正确的分词器
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # 如果模型太新找不到，默认回退到 cl100k_base
        encoding = tiktoken.get_encoding("cl100k_base")

    tokens = encoding.encode(text)
    return len(tokens)


if __name__ == '__main__':
    test = get_prompt("system_prompt")
    c = count_openai_tokens(test)
    print(c)