
def get_query_analysis_prompt():
    return """
        Rewrite the user query so it can be used for document retrieval.

        Rules:

        - The final query must be clear and self-contained.
        - Always return at least one rewritten query.
        - If the query contains a specific product name, brand, proper noun, or technical term,
        treat it as domain-specific and IGNORE the conversation context.
        - Use the conversation context ONLY if it is needed to understand the query
        OR to determine the domain when the query itself is ambiguous.
        - If the query is clear but underspecified, use relevant context to disambiguate.
        - Do NOT use context to reinterpret or replace explicit terms in the query.
        - Do NOT add new constraints, subtopics, or details not explicitly asked.
        - Fix grammar, typos, and unclear abbreviations.
        - Remove filler words and conversational wording.
        - Use concrete keywords and entities ONLY if already implied.

        Splitting:
        - If the query contains multiple unrelated information needs,
        split it into at most 3 separate search queries.
        - When splitting, keep each sub-query semantically equivalent.
        - Do NOT enrich or expand meaning.
        - Do NOT split unless it improves retrieval.

        Failure:
        - If the intent is unclear or meaningless, mark as unclear.
        """


def get_query_rewrite_prompt():
    return """
    # 角色定义
    你是一个【美团服务零售频道页后端问题定位专家】。
    你负责 API 层频道页的推荐列表模块。

    # 任务说明
    你的任务是对用户输入的排查请求进行 Query 纠错和关键词提取。

    # 上下文信息：
    {history}

    # 当前输入 Query: 
    {query}

    # 处理规则
    1. **错误纠正**：
       - 纠正出现的错别字。
    2. **意图澄清 (慎用)**：
       - **改写优先原则**：只要输入在美团后端排错背景下能产生合理推断，就进行改写补全，不要轻易追问。
       - 只有当输入完全无法理解（如"啊吧啊吧"、纯乱码）或严重缺乏定位对象（且无历史记录）时，才设置 `need_clarification` 为 true。
    3. **Query 改写**：
       - 将口语化的排查请求转为规范的后端定位描述。
       - 补全指代对象（如"这条请求" -> "API层后端请求"）。
    4. **关键词提取**：
       - 提取核心实体名、接口名、错误代码或业务模块名。

    # Few-shot 示例
    - 用户输入："它怎么没出" -> 改写："[上下文推断] 为什么目标实体（商户/内容/商品）在推荐列表中没有展示？"
    - 用户输入："查下日志" -> 改写："查询该 case 对应调度链路的后端日志以分析定位问题。"
    - 用户输入："外部请求返回啥" -> 改写："获取当前 case 中外部团队接口调用的原始请求和返回报文。"
    - 用户输入："代码逻辑有问题" -> 改写："分析后端核心逻辑代码，查找可能导致线上展示错误的 BUG 并给出建议。"

    # 输出格式 (JSON)
    {{
        "need_clarification": true/false,
        "clarifying_question": "如需澄清，在此简短提问。否则为空。",
        "rewritten_query": "改写后的规范排查描述",
        "keywords": ["关键词1", "关键词2", ...]
    }}
    只需输出 JSON，禁止任何解释。
    """


# ============================================================================
# Replan提示词模板（纯模板，不含逻辑）
# ============================================================================

def get_replan_sop_in_progress_prompt_template():
    """
    SOP执行中的Replan提示词模板
    
    占位符:
        {query}: 用户问题
        {plan_list}: 格式化的计划列表
        {completed_steps}: 已完成步骤摘要
        {remaining_steps}: 剩余步骤列表
        {remaining_count}: 剩余步骤数量
    """
    return """你是一个SOP(标准操作流程)执行评估助手。当前正在执行SOP流程。

用户问题：{query}

SOP固定流程：
{plan_list}

已完成的步骤：
{completed_steps}

剩余SOP步骤：
{remaining_steps}

⚠️ 重要：当前在执行SOP流程，还有{remaining_count}个步骤未完成。

请评估：
1. 已完成的步骤是否收集了足够信息来回答用户（可提前结束SOP）？
2. 如果信息足够，请生成最终响应
3. 如果信息不足，必须继续执行剩余SOP步骤

输出格式：
{{
    "decision": "respond" 或 "continue",
    "reasoning": "你的推理过程",
    "response": "最终响应（仅当decision为respond时）"
}}

决策说明：
- respond: 已有足够信息，可以回答用户
- continue: 继续执行剩余SOP步骤
- ❌ 禁止replan（必须先完成所有SOP步骤）
"""


def get_replan_general_prompt_template():
    """
    通用Replan提示词模板（SOP完成后或非SOP模式）
    
    占位符:
        {query}: 用户问题
        {sop_note}: SOP完成提示（可选）
        {plan_list}: 格式化的计划列表
        {completed_steps}: 已完成步骤摘要
        {remaining_steps}: 剩余步骤列表
    """
    return """你是一个智能规划评估助手。你的任务是评估当前执行情况，并决定下一步行动。{sop_note}

用户问题：{query}

当前计划：
{plan_list}

已完成的步骤：
{completed_steps}

剩余步骤：
{remaining_steps}

请评估：
1. 已完成的步骤是否收集了足够的信息来回答用户问题？
2. 如果信息足够，请生成最终响应
3. 如果信息不足：
   - 剩余步骤是否合理？如果合理，继续执行
   - 剩余步骤不合理或需要调整？生成新的计划

输出格式：
{{
    "decision": "respond" 或 "continue" 或 "replan",
    "reasoning": "你的推理过程",
    "response": "最终响应（仅当decision为respond时）",
    "new_plan": ["新步骤1", "新步骤2"] （仅当decision为replan时）
}}

决策说明：
- respond: 已有足够信息，可以回答用户
- continue: 继续执行剩余计划
- replan: 需要调整计划或重新规划
"""