from idlelib.undo import Command

from langchain.agents import create_agent
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from datetime import datetime
from langgraph.errors import GraphInterrupt
import time
import traceback

from src.config.llm import q_max, get_gpt_model, mt_llm
from src.graph_state import AgentState, Plan
from src.prompt.plan import planner_prompt_template
from src.tools import check_low_star_merchant, check_sensitive_merchant
from src.models.execution_result import (
    StepExecutionResult,
    StepStatus,
    ToolCall,
    PlanExecutionSummary
)


def planning_node(state: AgentState):
    """生成执行计划 - 根据intent动态选择prompt"""
    from langchain_core.messages import AIMessage
    from src.config.sop_loader import get_sop_loader
    
    faq_query = state['faq_query']
    intent = state.get('intent', 'default')
    
    # ⭐ 从SOPLoader获取planning prompt
    sop_loader = get_sop_loader()
    prompt_template_text = sop_loader.get_planning_prompt(intent)
    
    # 如果没有专业prompt，降级到通用prompt
    if not prompt_template_text:
        prompt_template_text = planner_prompt_template
        print(f"[Planning] Using default prompt (no custom for '{intent}')")
    else:
        print(f"[Planning] Using custom prompt for '{intent}'")
    
    # 准备parser和格式化
    plan_parser = JsonOutputParser(pydantic_object=Plan)
    format_instructions = plan_parser.get_format_instructions()
    
    final_prompt = prompt_template_text.format(
        query=faq_query,
        format_instructions=format_instructions
    )
    
    # 调用LLM
    planner_prompt = PromptTemplate(
        template="{text}",
        input_variables=["text"]
    )
    chain = planner_prompt | q_max | JsonOutputParser()
    result = chain.invoke({"text": final_prompt})
    
    steps = result.get('steps', [])
    
    # 📝 添加计划生成消息
    plan_message = AIMessage(
        content=f"📋 [{intent}] 已生成执行计划，共{len(steps)}个步骤:\n" + 
                "\n".join([f"{i+1}. {step}" for i, step in enumerate(steps)])
    )
    
    return {
        "plan": steps,
        "current_step": 0,
        "messages": [plan_message]
    }


def plan_executor_node(state: AgentState):
    """增强版计划执行节点 - 支持Human-in-the-Loop"""
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    
    # 检查是否已完成所有步骤
    if current_step >= len(plan):
        print(f"[PlanExecutor] 所有步骤已完成")
        return finalize_execution(state)
    
    step_description = plan[current_step]
    
    # 初始化步骤执行结果
    step_result = StepExecutionResult(
        step_index=current_step,
        step_description=step_description,
        status=StepStatus.RUNNING,
        start_time=datetime.now(),
        input_context={
            "query": state.get("query"),
            "previous_steps": len(state.get("step_results", [])),
            "faq_context": state.get("faq_response")
        }
    )
    
    # 📝 添加消息
    from langchain_core.messages import AIMessage
    messages_to_add = []
    
    # ⭐ 检查是否是恢复执行（从ask_human返回）
    # 通过检查messages中的最后一条HumanMessage来判断
    messages = state.get("messages", [])
    user_input = None
    
    if messages and len(messages) >= 2:
        # 检查最后两条消息是否是 AIMessage(问题) + HumanMessage(回复)
        if (messages[-2].__class__.__name__ == "AIMessage" and 
            "⏸️" in messages[-2].content and
            messages[-1].__class__.__name__ == "HumanMessage"):
            user_input = messages[-1].content
            print(f"[Executor] 检测到用户回复: {user_input}")
            
            # 添加恢复消息
            resume_message = AIMessage(
                content=f"▶️ 收到您的回复，继续执行步骤 {current_step + 1}"
            )
            messages_to_add.append(resume_message)
    
    if not user_input:
        # 首次执行此步骤，添加开始消息
        start_message = AIMessage(
            content=f"🔄 开始执行步骤 {current_step + 1}/{len(plan)}: {step_description}"
        )
        messages_to_add.append(start_message)
    
    print(f"[执行] 步骤 {current_step + 1}/{len(plan)}: {step_description}")
    
    # 准备Agent系统提示
    system_prompt = build_executor_prompt(state, current_step, step_description)
    
    # ⭐ 如果有用户输入，注入到prompt中
    if user_input:
        system_prompt += f"\n\n【用户提供的信息】\n{user_input}\n请使用这个信息完成当前任务。"
    
    # 创建Agent
    agent = create_agent(
        system_prompt=system_prompt,
        model=mt_llm("gpt-4.1"),
        tools=[check_low_star_merchant, check_sensitive_merchant],
    )
    
    # 执行
    start_exec = time.time()
    execution_result = agent.invoke({"input": step_description})
    exec_duration = (time.time() - start_exec) * 1000
    
    output = execution_result["messages"][-1].content
    
    # ⭐ 检查是否需要询问用户
    if "ask_human" in output.lower():
        print(f"[中断] 步骤 {current_step + 1} 需要用户输入")
        
        # 提取问题（Agent应该在输出中说明需要什么信息）
        question = output.replace("ask_human", "").strip()
        if not question:
            question = "请提供执行此步骤所需的信息"
        
        # 更新步骤状态为需要澄清
        step_result.status = StepStatus.NEED_CLARIFICATION
        step_result.interrupt_question = question
        step_result.end_time = datetime.now()
        step_result.duration_ms = exec_duration
        
        # 添加中断消息
        interrupt_message = AIMessage(
            content=f"⏸️ 步骤 {current_step + 1} 需要更多信息\n{question}"
        )
        messages_to_add.append(interrupt_message)
        
        # ⭐ 中断：不增加current_step，保持在当前步骤
        return Command(goto="ask_human", update={
            "response": question,
            "return_to": "plan_executor",
            "need_clarification": True,
            "step_results": [step_result],
            "messages": messages_to_add,
            # current_step 不变！用户回复后会重新执行这一步
        })
    
    # 正常执行完成
    # 提取工具调用信息
    tool_calls = extract_tool_calls(execution_result)
    
    # 更新结果
    step_result.status = StepStatus.SUCCESS
    step_result.end_time = datetime.now()
    step_result.duration_ms = exec_duration
    step_result.agent_response = str(output)
    step_result.output_result = output[:500] if output else ""
    
    # ⭐ 打印成功日志和工具结果
    print(f"[成功] 步骤 {current_step + 1} 完成,耗时 {exec_duration:.2f}ms")
    
    # ⭐ 如果有工具调用，打印工具结果
    if tool_calls:
        print(f"[工具调用] 本步骤调用了 {len(tool_calls)} 个工具:")
        for tool_call in tool_calls:
            print(f"  • {tool_call.tool_name}")
            # 打印关键结果（如果有）
            if tool_call.result:
                try:
                    import json
                    result_data = tool_call.result if isinstance(tool_call.result, dict) else {}
                    
                    # 针对不同工具打印关键信息
                    if 'check_sensitive_merchant' in tool_call.tool_name:
                        is_violated = result_data.get('is_violated', 'N/A')
                        risk_score = result_data.get('risk_score', 'N/A')
                        risk_score_v2 = result_data.get('risk_score_v2', 'N/A')
                        print(f"    → is_violated={is_violated}, risk_score={risk_score}, risk_score_v2={risk_score_v2}")
                    
                    elif 'check_low_star_merchant' in tool_call.tool_name:
                        is_low_star = result_data.get('is_low_star', 'N/A')
                        shop_star = result_data.get('shop_star', 'N/A')
                        print(f"    → is_low_star={is_low_star}, shop_star={shop_star}")
                    
                    elif 'get_trace_context' in tool_call.tool_name:
                        scene_code = result_data.get('scene_code', 'N/A')
                        exp_count = len(result_data.get('experiments', []))
                        print(f"    → scene_code={scene_code}, 命中{exp_count}个实验")
                    
                    elif 'get_visit_record' in tool_call.tool_name:
                        count = result_data.get('count', 0)
                        print(f"    → 找到{count}条访问记录")
                    
                    else:
                        # 其他工具，打印通用信息
                        # 取前3个键值对
                        keys = list(result_data.keys())[:3]
                        summary = {k: result_data[k] for k in keys if k in result_data}
                        if summary:
                            print(f"    → {summary}")
                
                except Exception as e:
                    # 如果解析失败，跳过
                    pass
    
    print()  # 空行
    
    # 📝 添加成功消息
    result_summary = step_result.output_result[:200] if step_result.output_result else "执行完成"
    tools_used = f" (使用了{len(tool_calls)}个工具)" if tool_calls else ""
    
    success_message = AIMessage(
        content=f"✅ 步骤 {current_step + 1} 完成{tools_used}\n{result_summary}"
    )
    messages_to_add.append(success_message)
    
    # ⭐ 成功后才增加current_step
    return {
        "current_step": current_step + 1,
        "step_results": [step_result],
        "messages": messages_to_add,
        "need_clarification": False,
        "past_steps": [(step_description, step_result.agent_response)]
    }


def build_executor_prompt(state: AgentState, step_index: int, task: str) -> str:
    """构建执行器提示词"""
    previous_results = state.get("step_results", [])
    context = ""
    if previous_results:
        context = "\n".join([
            f"步骤{i+1}: {r.step_description} -> {r.output_result or '无结果'}"
            for i, r in enumerate(previous_results[-3:])  # 只显示最近3步
        ])

    return f"""你是一个严格的计划执行节点。
你的职责: 仅执行当前步骤,不进行额外推理。

用户问题: {state['query']}
当前执行: 步骤 {step_index + 1} - {task}

前序步骤上下文:
{context or '无'}

要求:
1. 严格按照当前步骤描述执行
2. 如果需要调用工具,请直接调用
3. 如果信息不足,输出 "ask_human"，询问人类。并拼接你需要询问的问题
4. 不要重复前面步骤的工作
"""


def extract_tool_calls(result: dict) -> list:
    """从Agent结果中提取工具调用信息"""
    tool_calls_list = []
    messages = result.get("messages", [])

    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls_list.append(ToolCall(
                    tool_name=tc.get("name", "unknown"),
                    arguments=tc.get("args", {}),
                    result=tc.get("result"),
                    error=tc.get("error")
                ))

    return tool_calls_list


def extract_output(result: dict) -> str:
    """提取输出结果"""
    if "output" in result:
        return str(result["output"])
    if "messages" in result and result["messages"]:
        last_msg = result["messages"][-1]
        if hasattr(last_msg, "content"):
            return last_msg.content
    return ""


def finalize_execution(state: AgentState) -> dict:
    """完成执行,生成摘要"""
    from langchain_core.messages import AIMessage
    
    step_results = state.get("step_results", [])

    summary = PlanExecutionSummary(
        # plan_id=state.get("thread_id", "unknown"),
        query=state.get("query", ""),
        intent=state.get("intent"),
        is_sop=state.get("is_sop_matched", False),
        total_steps=len(state.get("plan", [])),
        plan_steps=state.get("plan", []),
        completed_steps=len([r for r in step_results if r.status == StepStatus.SUCCESS]),
        failed_steps=len([r for r in step_results if r.status == StepStatus.FAILED]),
        skipped_steps=len([r for r in step_results if r.status == StepStatus.SKIPPED]),
        overall_status=StepStatus.SUCCESS if all(
            r.status == StepStatus.SUCCESS for r in step_results
        ) else StepStatus.FAILED,
        final_response=state.get("response", "")
    )

    if step_results:
        summary.start_time = step_results[0].start_time
        summary.end_time = step_results[-1].end_time
        if summary.start_time and summary.end_time:
            summary.total_duration_ms = (
                summary.end_time - summary.start_time
            ).total_seconds() * 1000
    
    # 📝 添加完成消息
    status_emoji = "🎉" if summary.overall_status == StepStatus.SUCCESS else "⚠️"
    completion_message = AIMessage(
        content=f"{status_emoji} 所有步骤已完成\n" +
                f"• 总计: {summary.total_steps} 步\n" +
                f"• 成功: {summary.completed_steps} 步\n" +
                f"• 失败: {summary.failed_steps} 步\n" +
                f"• 总耗时: {summary.total_duration_ms:.0f}ms"
    )

    return {
        "execution_summary": summary,
        "messages": [completion_message]
    }


def replan_node(state: AgentState) -> dict:
    """
    重新规划节点 - 评估执行结果并决定下一步行动
    
    职责：
    1. 评估已执行步骤的结果
    2. 判断是否已收集足够信息可以回答用户
    3. 判断是否需要调整计划或重新规划
    4. 决定：继续执行 / 重新规划 / 结束并响应
    
    ⭐ SOP模式：只有执行完所有SOP步骤后才允许replan
    """
    from langchain_core.messages import AIMessage, SystemMessage
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    
    query = state.get("query", "")
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    step_results = state.get("step_results", [])
    is_sop_matched = state.get("is_sop_matched", False)
    
    # ⭐ 检查是否所有SOP步骤已执行完毕
    # 通过比较step_results数量和原始plan长度判断
    # 如果step_results中的步骤都来自原始plan，说明还在SOP阶段
    sop_completed = False
    if is_sop_matched and step_results:
        # 检查是否有step_index >= len(plan)的结果（说明已经replan过）
        max_step_index = max([r.step_index for r in step_results])
        # 或者检查current_step是否已经到达或超过原始plan长度
        if current_step >= len(plan):
            sop_completed = True
            print(f"[Replan] SOP已全部执行完毕 ({len(plan)}步），现在允许replan")
    
    # 如果还没有执行任何步骤，直接继续
    if not step_results:
        return {}
    
    # 构建已完成步骤的摘要
    completed_steps_summary = []
    for result in step_results:
        status = "✅ 成功" if result.status == "success" else "❌ 失败"
        summary = f"{status} 步骤{result.step_index + 1}: {result.step_description}"
        if result.output_result:
            summary += f"\n   结果: {result.output_result[:150]}"
        if result.error_message:
            summary += f"\n   错误: {result.error_message[:100]}"
        completed_steps_summary.append(summary)
    
    # 剩余步骤
    remaining_steps = plan[current_step:] if current_step < len(plan) else []
    
    # ⭐ 根据SOP状态构建不同的提示
    if is_sop_matched and not sop_completed:
        # SOP执行中：不允许replan
        replan_prompt = f"""你是一个SOP(标准操作流程)执行评估助手。当前正在执行SOP流程。

用户问题：{query}

SOP固定流程：
{chr(10).join([f"{i+1}. {step}" for i, step in enumerate(plan)])}

已完成的步骤：
{chr(10).join(completed_steps_summary)}

剩余SOP步骤：
{chr(10).join([f"{i+current_step+1}. {step}" for i, step in enumerate(remaining_steps)]) if remaining_steps else "无"}

⚠️ 重要：当前在执行SOP流程，还有{len(remaining_steps)}个步骤未完成。

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
    else:
        # 非SOP模式 或 SOP已完成：允许replan
        sop_completed_note = "（SOP已全部执行完毕，可以重新规划）" if is_sop_matched else ""
        replan_prompt = f"""你是一个智能规划评估助手。你的任务是评估当前执行情况，并决定下一步行动。{sop_completed_note}

用户问题：{query}

当前计划：
{chr(10).join([f"{i+1}. {step}" for i, step in enumerate(plan)])}

已完成的步骤：
{chr(10).join(completed_steps_summary)}

剩余步骤：
{chr(10).join([f"{i+current_step+1}. {step}" for i, step in enumerate(remaining_steps)]) if remaining_steps else "无"}

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

    # 调用LLM进行决策
    messages = [
        SystemMessage(content="你是一个智能规划评估助手，擅长分析执行结果并做出合理决策。"),
        {"role": "user", "content": replan_prompt}
    ]
    
    try:
        result = q_max.invoke(messages)
        
        # 解析LLM响应
        import json
        try:
            decision_data = json.loads(result.content)
        except:
            # 如果JSON解析失败，使用JsonOutputParser
            from langchain_core.output_parsers import StrOutputParser
            parser = StrOutputParser()
            content = parser.invoke(result)
            # 尝试从content中提取JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                decision_data = json.loads(json_match.group())
            else:
                # 默认继续执行
                decision_data = {
                    "decision": "continue",
                    "reasoning": "无法解析LLM响应，默认继续执行"
                }
        
        decision = decision_data.get("decision", "continue")
        reasoning = decision_data.get("reasoning", "")
        
        print(f"\n[Replan] 决策: {decision}")
        print(f"[Replan] 推理: {reasoning}")
        
        messages_to_add = []
        
        # 根据决策返回不同的结果
        if decision == "respond":
            # 已有足够信息，生成最终响应
            response_text = decision_data.get("response", "")
            
            response_message = AIMessage(
                content=f"💡 已收集足够信息，生成最终答案\n{response_text}"
            )
            messages_to_add.append(response_message)
            
            return {
                "response": response_text,
                "messages": messages_to_add,
                # 标记为完成，停止继续执行
                "current_step": len(plan)  # 设置为计划长度，触发完成
            }
        
        elif decision == "replan":
            # 需要重新规划
            new_plan = decision_data.get("new_plan", [])
            
            replan_message = AIMessage(
                content=f"🔄 需要调整计划\n原因: {reasoning}\n新计划:\n" +
                        "\n".join([f"{i+1}. {step}" for i, step in enumerate(new_plan)])
            )
            messages_to_add.append(replan_message)
            
            return {
                "plan": new_plan,
                "current_step": 0,  # 重置到第一步
                "messages": messages_to_add
            }
        
        else:  # continue
            # 继续执行剩余计划
            continue_message = AIMessage(
                content=f"▶️ 继续执行剩余计划\n原因: {reasoning}"
            )
            messages_to_add.append(continue_message)
            
            return {
                "messages": messages_to_add
            }
    
    except Exception as e:
        print(f"[Replan] 错误: {e}")
        import traceback
        traceback.print_exc()
        
        # 出错时默认继续执行
        error_message = AIMessage(
            content=f"⚠️ 评估过程出错，继续执行原计划\n错误: {str(e)[:100]}"
        )
        
        return {
            "messages": [error_message]
        }
