"""
项目常量定义
集中管理各模块中使用的魔法数字和固定字符串
"""

# 输出截断长度
MAX_STEP_OUTPUT_LENGTH = 500       # 步骤输出存入 step_result 的最大长度
MAX_OUTPUT_PREVIEW_LENGTH = 200    # 步骤摘要展示的最大长度
MAX_AGENT_RESPONSE_PREVIEW = 300   # agent_response 展示的最大长度
MAX_REPLAN_SUMMARY_LENGTH = 150    # replan 中步骤结果摘要的最大长度
MAX_REPLAN_ERROR_LENGTH = 100      # replan 中错误信息的最大长度

# 检索参数
DEFAULT_RETRIEVAL_LIMIT = 3        # 向量检索默认返回条数
DEFAULT_SCORE_THRESHOLD = 0.75     # 向量检索默认分数阈值

# Embedding
EMBEDDING_VECTOR_SIZE = 1536       # text-embedding-v1 向量维度
