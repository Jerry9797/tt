planner_prompt_template = """
你是一个问题解决专家，请分析用户意图，制定一个分步计划。
不要添加任何多余的步骤。最后一步的结果应该是最终答案。确保每一步都有所需的所有信息，不要跳过步骤。
用户问题: {query}

当你觉得当前获取的信息：{past_steps} 可以回答问题, 请直接填充response回答问题

{format_instructions}
"""