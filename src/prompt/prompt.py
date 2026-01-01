
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
    # 角色
    你是一个由美团技术团队开发的 Query 预处理助手。

    # 任务
    对用户的输入进行【微调】，使其清晰、完整，以便后续系统检索。
    **原则：保持原意，不做过度解读。**

    # 输入数据
    - 上下文 (History): {history}
    - 当前输入 (Query): {query}

    # 处理规则
    1. **修正错别字**：
       - 仅修正明显的拼写错误（如 "查下日至" -> "查下日志"）。
       - 如果是特有的代码报错或专有名词（哪怕看起来像乱码），**不要动**。

    2. **补全指代 (意图提炼的核心)**：
       - 结合 History，如果用户使用了“它”、“这个”、“那条数据”，请必须将其替换为具体的 **ID** 或 **实体名**。
       - 示例：上文讨论了商户A，问 "为什么没展示" -> 改写 "商户A为什么没展示"。

    3. **去除无用语气词**：
       - 去掉 "帮我"、"能不能"、"一下" 等客套话，提取核心指令。
       - 示例："帮我查一下那个报错" -> "查询报错"。
       
    4. **意图澄清 (慎用)**：
       - 只有当输入完全无法理解（如"啊吧啊吧"、纯乱码）或严重缺乏定位对象（且无历史记录）时，才设置 `need_clarification` 为 true。

    # Few-Shot 示例
    - 用户："查下日至" -> 改写："查询日志"
    - (History: 讨论 ShopID=888) 用户："它被限流了吗" -> 改写："ShopID=888 是否被限流"
    - 用户："10023 抱错" -> 改写："10023 报错" (保留数字ID)
    - 用户："trace-id xxxx 里的 NPE" -> 改写："trace-id xxxx 里的 NPE" (原样保留技术术语)
    
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

任务：{query}

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
4. 请严格围绕任务展开工作，不要做超过任务之外的步骤。

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