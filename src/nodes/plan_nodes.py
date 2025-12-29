from langgraph.types import Command, interrupt

from langchain.agents import create_agent

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from datetime import datetime
import time

from src.config.llm import q_max, get_gpt_model, mt_llm, q_plus
from src.graph_state import AgentState, Plan
from src.prompt.plan import planner_prompt_template
from src.tools import (
    ALL_TOOLS,
    check_low_star_merchant, 
    check_sensitive_merchant,
    search_user_access_history,
    restore_user_scene,
    analyze_recall_chain,
    parse_user_query_params
)
from src.models.execution_result import (
    StepExecutionResult,
    StepStatus,
    ToolCall,
    PlanExecutionSummary,
    TokenUsage
)


async def planning_node(state: AgentState):
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
    
    # 调用LLM（异步）
    planner_prompt = PromptTemplate(
        template="{text}",
        input_variables=["text"]
    )
    chain = planner_prompt | q_max | JsonOutputParser()
    result = await chain.ainvoke({"text": final_prompt})
    
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


async def plan_executor_node(state: AgentState):
    """增强版计划执行节点 - 支持Human-in-the-Loop（异步版本）"""
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
    from langchain_core.messages import HumanMessage # Added for new logic
    messages_to_add = []
    
    # ⭐ 检查是否有用户刚刚的回复（用于恢复）
    user_input = None
    messages = state.get("messages", [])
    
    # 改进逻辑：倒序查找最近的一次 [AIMessage(⏸️) -> ... -> HumanMessage] 模式
    # 允许中间由 ReplanNode 插入的其他 AIMessage
    
    last_ask_index = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, AIMessage) and "⏸️" in str(msg.content):
            last_ask_index = i
            break
            
    if last_ask_index != -1:
        # 找到了最近的提问，检查其后是否有 HumanMessage
        # 通常 HumanMessage 应该在 Ask 之后
        for i in range(last_ask_index + 1, len(messages)):
            if isinstance(messages[i], HumanMessage):
                user_input = messages[i].content
                # 找到第一个 HumanMessage 即停止，视为回复
                break

    if user_input:
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
    
    # ⭐ 获取 MCP 工具并合并
    from src.mcp import get_mcp_manager
    
    mcp_manager = get_mcp_manager()
    mcp_tools = mcp_manager.get_all_tools()
    
    # 合并静态工具和 MCP 工具
    all_tools = ALL_TOOLS + mcp_tools
    
    if mcp_tools:
        print(f"[MCP] 已加载 {len(mcp_tools)} 个 MCP 工具")
    
    # 创建Agent
    agent = create_agent(
        system_prompt=system_prompt,
        # model=mt_llm("gpt-4.1"),
        model=q_plus,
        tools=all_tools,  # ⭐ 使用合并后的工具列表
    )
    
    # 执行（异步）
    start_exec = time.time()
    # ⭐ 使用 ainvoke 而不是 invoke，支持异步工具调用
    execution_result = await agent.ainvoke({
        "input": step_description,
        # "chat_history": state.get("messages", [])
    })
    exec_duration = (time.time() - start_exec) * 1000
    
    # ⭐ 提取 Token Usage
    token_usage = TokenUsage()
    if "messages" in execution_result and execution_result["messages"]:
        last_msg = execution_result["messages"][-1]
        if hasattr(last_msg, "response_metadata"):
            usage_data = last_msg.response_metadata.get("token_usage", {})
            if usage_data:
                token_usage = TokenUsage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0)
                )
                print(f"[资源] Token消耗: {token_usage.total_tokens} (Prompt: {token_usage.prompt_tokens}, Completion: {token_usage.completion_tokens})")
    
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
    step_result.token_usage = token_usage
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
                    
                    # ⭐ 用户日志工具结果打印
                    elif 'search_user_access_history' in tool_call.tool_name:
                        record_count = result_data.get('count', 0)
                        print(f"    → 找到{record_count}条访问记录")

                    elif 'restore_user_scene' in tool_call.tool_name:
                        if 'error' in result_data:
                            print(f"    → 还原失败: {result_data['error']}")
                        else:
                            merchant_count = len(result_data.get('merchants', []))
                            click_count = len(result_data.get('click_records', []))
                            print(f"    → 展示{merchant_count}个商户, {click_count}次点击, 页面: {result_data.get('display_info', {}).get('page')}")

                    elif 'analyze_recall_chain' in tool_call.tool_name:
                        issue = result_data.get('root_cause', 'N/A')
                        print(f"    → 根因={issue}")
                    
                    elif 'parse_user_query_params' in tool_call.tool_name:
                        print(f"    → 提取参数: {result_data}")
                    
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

    # ⭐ 将对话历史也放入System Prompt中
    chat_history_str = ""
    messages = state.get("messages", [])
    if messages:
        chat_history_str = "\n".join([
            f"{msg.type}: {msg.content}" 
            for msg in messages 
            if msg.type in ['human', 'ai']
        ])

    return f"""你是一个严格的计划执行节点。
你的职责: 仅执行当前步骤,不进行额外推理。

用户问题: {state['query']}
当前执行: 步骤 {step_index + 1} - {task}

前序步骤上下文:
{context or '无'}

对话历史:
{chat_history_str or '无'}

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

    # ⭐ 聚合 Token Usage
    total_tokens = TokenUsage()
    for res in step_results:
        if res.token_usage:
            total_tokens.add(res.token_usage)
    summary.total_token_usage = total_tokens

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
                f"• 总耗时: {summary.total_duration_ms:.0f}ms\n" +
                f"• Token消耗: {summary.total_token_usage.total_tokens}"
    )

    return {
        "execution_summary": summary,
        "messages": [completion_message]
    }


async def replan_node(state: AgentState) -> dict:
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
    
    # ⭐ 从prompt模块获取提示词模板（不含逻辑）
    from src.prompt.prompt import (
        get_replan_sop_in_progress_prompt_template,
        get_replan_general_prompt_template
    )
    
    # ⭐ 组装逻辑在这里（调用方负责）
    if is_sop_matched and not sop_completed:
        # SOP执行中：使用SOP模板
        prompt_template = get_replan_sop_in_progress_prompt_template()
        replan_prompt = prompt_template.format(
            query=query,
            plan_list="\n".join([f"{i+1}. {step}" for i, step in enumerate(plan)]),
            completed_steps="\n".join(completed_steps_summary),
            remaining_steps="\n".join([f"{i+current_step+1}. {step}" for i, step in enumerate(remaining_steps)]) if remaining_steps else "无",
            remaining_count=len(remaining_steps)
        )
    else:
        # 非SOP或SOP已完成：使用通用模板
        prompt_template = get_replan_general_prompt_template()
        sop_note = "（SOP已全部执行完毕，可以重新规划）" if is_sop_matched else ""
        replan_prompt = prompt_template.format(
            query=query,
            sop_note=sop_note,
            plan_list="\n".join([f"{i+1}. {step}" for i, step in enumerate(plan)]),
            completed_steps="\n".join(completed_steps_summary),
            remaining_steps="\n".join([f"{i+current_step+1}. {step}" for i, step in enumerate(remaining_steps)]) if remaining_steps else "无"
        )

    # 调用LLM进行决策（异步）
    messages = [
        SystemMessage(content="你是一个智能规划评估助手，擅长分析执行结果并做出合理决策。"),
        {"role": "user", "content": replan_prompt}
    ]
    
    try:
        result = await q_max.ainvoke(messages)
        
        # 解析LLM响应
        import json
        import re
        
        decision_data = None
        
        # 策略1: 直接解析 result.content
        try:
            decision_data = json.loads(result.content)
        except json.JSONDecodeError:
            pass
        
        # 策略2: 使用正则提取 JSON 块
        if not decision_data:
            try:
                json_match = re.search(r'\{.*\}', result.content, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    # 尝试修复常见的 JSON 格式问题
                    # 1. 移除 JSON 中的注释
                    json_str = re.sub(r'//.*?\n|/\*.*?\*/', '', json_str, flags=re.DOTALL)
                    # 2. 移除尾随逗号
                    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                    decision_data = json.loads(json_str)
            except (json.JSONDecodeError, AttributeError) as e:
                print(f"[Replan] JSON 解析失败: {e}")
        
        # 策略3: 使用 LangChain 的 JsonOutputParser 强制解析
        if not decision_data:
            try:
                parser = JsonOutputParser()
                decision_data = parser.invoke(result)
            except Exception as e:
                print(f"[Replan] JsonOutputParser 失败: {e}")
        
        # 最后的兜底: 默认继续执行
        if not decision_data:
            print(f"[Replan] 无法解析响应，原始内容: {result.content[:200]}")
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
    
    # ⭐ 从prompt模块获取提示词模板（不含逻辑）
    from src.prompt.prompt import (
        get_replan_sop_in_progress_prompt_template,
        get_replan_general_prompt_template
    )
    
    # ⭐ 组装逻辑在这里（调用方负责）
    if is_sop_matched and not sop_completed:
        # SOP执行中：使用SOP模板
        prompt_template = get_replan_sop_in_progress_prompt_template()
        replan_prompt = prompt_template.format(
            query=query,
            plan_list="\n".join([f"{i+1}. {step}" for i, step in enumerate(plan)]),
            completed_steps="\n".join(completed_steps_summary),
            remaining_steps="\n".join([f"{i+current_step+1}. {step}" for i, step in enumerate(remaining_steps)]) if remaining_steps else "无",
            remaining_count=len(remaining_steps)
        )
    else:
        # 非SOP或SOP已完成：使用通用模板
        prompt_template = get_replan_general_prompt_template()
        sop_note = "（SOP已全部执行完毕，可以重新规划）" if is_sop_matched else ""
        replan_prompt = prompt_template.format(
            query=query,
            sop_note=sop_note,
            plan_list="\n".join([f"{i+1}. {step}" for i, step in enumerate(plan)]),
            completed_steps="\n".join(completed_steps_summary),
            remaining_steps="\n".join([f"{i+current_step+1}. {step}" for i, step in enumerate(remaining_steps)]) if remaining_steps else "无"
        )

    # 调用LLM进行决策
    messages = [
        SystemMessage(content="你是一个智能规划评估助手，擅长分析执行结果并做出合理决策。"),
        {"role": "user", "content": replan_prompt}
    ]
    
    try:
        result = q_max.invoke(messages)
        
        # 解析LLM响应
        import json
        import re
        
        decision_data = None
        
        # 策略1: 直接解析 result.content
        try:
            decision_data = json.loads(result.content)
        except json.JSONDecodeError:
            pass
        
        # 策略2: 使用正则提取 JSON 块
        if not decision_data:
            try:
                json_match = re.search(r'\{.*\}', result.content, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    # 尝试修复常见的 JSON 格式问题
                    # 1. 移除 JSON 中的注释
                    json_str = re.sub(r'//.*?\n|/\*.*?\*/', '', json_str, flags=re.DOTALL)
                    # 2. 移除尾随逗号
                    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                    decision_data = json.loads(json_str)
            except (json.JSONDecodeError, AttributeError) as e:
                print(f"[Replan] JSON 解析失败: {e}")
        
        # 策略3: 使用 LangChain 的 JsonOutputParser 强制解析
        if not decision_data:
            try:
                parser = JsonOutputParser()
                decision_data = parser.invoke(result)
            except Exception as e:
                print(f"[Replan] JsonOutputParser 失败: {e}")
        
        # 最后的兜底: 默认继续执行
        if not decision_data:
            print(f"[Replan] 无法解析响应，原始内容: {result.content[:200]}")
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
