import json
import logging
import re
import time
from datetime import datetime

from langgraph.types import Command
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.config.llm import get_gpt_model, mt_llm
from src.config.sop_loader import get_sop_loader
from src.graph_state import AgentState, Plan
from src.tools import (
    ALL_TOOLS,
)
from src.models.execution_result import (
    StepExecutionResult,
    StepStatus,
    ToolCall,
    PlanExecutionSummary,
    TokenUsage
)

logger = logging.getLogger(__name__)
sop_loader = get_sop_loader()
_ASK_HUMAN_RE = re.compile(r"^\[ASK_HUMAN\]\s*:?\s*(.*)", re.MULTILINE)


def _extract_token_usage(response) -> TokenUsage:
    """从 LLM 响应中提取 token 使用量。"""
    if hasattr(response, "response_metadata"):
        usage_data = response.response_metadata.get("token_usage", {})
        if usage_data:
            return TokenUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
    return TokenUsage()


async def planning_node(state: AgentState):
    """生成执行计划 - 根据intent动态选择prompt"""
    rewritten_query = state['rewritten_query']
    intent = state.get('intent', 'default')

    # ⭐ 从SOPLoader获取planning prompt（使用模块级 sop_loader）
    plan_prompt = sop_loader.get_planning_prompt(intent)

    plan_parser = JsonOutputParser(pydantic_object=Plan)
    format_instructions = plan_parser.get_format_instructions()

    from src.prompt.prompt_loader import get_prompt
    plan_messages = [SystemMessage(content=get_prompt("system_prompt"))]
    if plan_prompt:
        plan_messages.append(SystemMessage(content=plan_prompt))
    plan_messages.extend([
        HumanMessage(content=rewritten_query),
        SystemMessage(content=f"所有回复必须遵循以下格式：\n{format_instructions}"),
    ])
    prompt = ChatPromptTemplate.from_messages(plan_messages)
    chain = prompt | get_gpt_model("gpt-4.1-mini") | plan_parser
    try:
        result = await chain.ainvoke({})
    except Exception:
        logger.warning("Plan parsing failed, retrying once")
        result = await chain.ainvoke({})
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


async def plan_executor_node(state: AgentState, tools: list = None):
    """
    执行当前 plan step。

    状态协议：
    - 普通执行时，从 `plan[current_step]` 读取当前任务。
    - 恢复执行时，只通过 `resume_input` 判断，避免再依赖旧的布尔标记推断上下文。
    - 真正完成步骤后才把 `StepExecutionResult` 追加进 `step_results`。
    - 如果中途需要澄清，则只写入中断态并跳到 `ask_human`，不落半成品步骤结果。
    """
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    
    # 检查是否已完成所有步骤
    if current_step >= len(plan):
        logger.info("All plan steps completed, moving to finalization")
        return Command(goto="finalize_execution_node")
    
    step_description = plan[current_step]
    
    # 初始化步骤执行结果
    step_result = StepExecutionResult(
        step_index=current_step,
        step_description=step_description,
        status=StepStatus.RUNNING,
        start_time=datetime.now()
    )

    
    # 当前轮次新增的 AI 提示消息会被拼进 prompt，同时也会回写消息历史。
    messages_to_add = []
    
    # ⭐ 使用 resume_input 判断是否处于中断恢复状态
    user_input = state.get("resume_input")
    is_resuming = bool(user_input)

    if is_resuming:
        logger.info("Resuming plan execution for step %s", current_step + 1)
        # 恢复执行时，用一条显式 AIMessage 把"刚收到过补充信息"写进上下文，
        # 这样执行 prompt 里能读到状态转换，而不只是孤立的一句用户输入。
        resume_message = AIMessage(
            content=f"▶️ 收到您的回复，继续执行步骤 {current_step + 1}"
        )
        messages_to_add.append(resume_message)
    
    if not is_resuming:
        # 首次执行此步骤，添加开始消息
        start_message = AIMessage(
            content=f"🔄 开始执行步骤 {current_step + 1}/{len(plan)}: {step_description}"
        )
        messages_to_add.append(start_message)
    
    logger.info("Executing step %s/%s: %s", current_step + 1, len(plan), step_description)
    
    # 准备Agent系统提示（传递当前轮次的新消息）
    system_prompt = build_executor_prompt(state, current_step, step_description, messages_to_add)
    
    # ⭐ 使用预合并的工具（由 build_graph 通过 partial 注入），兜底回退到运行时组装
    if tools is not None:
        all_tools = tools
    else:
        from src.mcp import get_mcp_manager
        mcp_tools = get_mcp_manager().get_all_tools()
        all_tools = ALL_TOOLS + mcp_tools
    logger.info("Using %s tools for step %s", len(all_tools), current_step + 1)

    # ⭐ 使用 bind_tools 替代 create_agent，固定 2 次 LLM 调用
    llm = get_gpt_model("gpt-4.1-mini").bind_tools(all_tools)
    tool_map = {t.name: t for t in all_tools}

    # 构建输入消息
    input_messages = [SystemMessage(content=system_prompt)]
    if user_input:
        input_messages.append(HumanMessage(content=user_input))

    # 执行（异步）
    start_exec = time.time()

    # 第1次调用：LLM 决定调哪些工具
    ai_response = await llm.ainvoke(input_messages)

    # 执行工具调用
    tool_messages = []
    if ai_response.tool_calls:
        for tc in ai_response.tool_calls:
            tool_func = tool_map.get(tc["name"])
            if tool_func:
                try:
                    result = await tool_func.ainvoke(tc["args"])
                except Exception as e:
                    result = f"工具调用失败: {e}"
            else:
                result = f"未找到工具: {tc['name']}"
            tool_messages.append(ToolMessage(
                content=str(result),
                tool_call_id=tc["id"],
            ))

    # 第2次调用：LLM 汇总工具结果生成最终输出
    if tool_messages:
        final_response = await llm.ainvoke(
            input_messages + [ai_response] + tool_messages
        )
    else:
        final_response = ai_response

    exec_duration = (time.time() - start_exec) * 1000
    # ⭐ 提取 Token Usage（累加两次 LLM 调用）
    token_usage = _extract_token_usage(ai_response)
    if tool_messages:
        token_usage.add(_extract_token_usage(final_response))
    if token_usage.total_tokens:
        logger.info(
            "Token usage total=%s prompt=%s completion=%s",
            token_usage.total_tokens,
            token_usage.prompt_tokens,
            token_usage.completion_tokens,
        )

    output = final_response.content
    
    # ⭐ 检查是否需要询问用户
    ask_match = _ASK_HUMAN_RE.search(output)
    if ask_match:
        logger.info("Step %s requires clarification", current_step + 1)

        # 提取问题（Agent应该在输出中说明需要什么信息）
        question = ask_match.group(1).strip()
        if not question:
            question = "请提供执行此步骤所需的信息"
        
        # 更新步骤状态为需要澄清
        # step_result.status = StepStatus.NEED_CLARIFICATION
        # step_result.interrupt_question = question
        # step_result.end_time = datetime.now()
        # step_result.duration_ms = exec_duration
        
        # 这里不把 RUNNING 的 step_result 落到 `step_results`。
        # 否则恢复后会同时存在"半成品 running 结果"和"最终 success 结果"，
        # 导致 execution summary 的统计失真。
        interrupt_message = AIMessage(
            content=f"⏸️ 步骤 {current_step + 1} 需要更多信息\n{question}"
        )
        messages_to_add.append(interrupt_message)
        
        # ⭐ 中断：不增加current_step，保持在当前步骤
        return Command(goto="ask_human", update={
            "clarification_question": question,
            "resume_target": "plan_executor_node",
            "awaiting_user_input": True,
            "resume_input": None,
            "messages": messages_to_add,
            # current_step 不变！用户回复后会重新执行这一步
        })
    
    # 正常执行完成
    # 提取工具调用信息
    tool_calls = []
    if ai_response.tool_calls:
        for tc in ai_response.tool_calls:
            tool_calls.append(ToolCall(
                tool_name=tc.get("name", "unknown"),
                arguments=tc.get("args", {}),
            ))
    
    # 更新结果
    step_result.status = StepStatus.SUCCESS
    step_result.end_time = datetime.now()
    step_result.duration_ms = exec_duration
    step_result.token_usage = token_usage
    step_result.agent_response = str(output)
    step_result.output_result = output[:500] if output else ""
    step_result.tool_calls = tool_calls
    
    # ⭐ 打印成功日志和工具结果
    logger.info("Step %s completed in %.2fms", current_step + 1, exec_duration)

    # 📝 添加成功消息
    result_summary = step_result.output_result[:200] if step_result.output_result else "执行完成"
    tools_used = f" (使用了{len(tool_calls)}个工具)" if tool_calls else ""
    
    success_message = AIMessage(
        content=f"✅ 步骤 {current_step + 1} 完成{tools_used}\n{result_summary}"
    )
    messages_to_add.append(success_message)
    
    # 只有真正执行成功后才推进 `current_step`，并清理可能残留的中断态字段。
    return {
        "current_step": current_step + 1,
        "step_results": [step_result],
        "messages": messages_to_add,
        "awaiting_user_input": False,
        "clarification_question": None,
        "resume_target": None,
        "resume_input": None,
    }




def format_message_history(messages: list, filter_types: list = None) -> str:
    """
    格式化消息历史为字符串
    
    Args:
        messages: 消息列表
        filter_types: 需要包含的消息类型，默认为 ['human', 'ai']
        
    Returns:
        格式化后的消息历史字符串
    """
    if not messages:
        return ""
    
    if filter_types is None:
        filter_types = ['human', 'ai']
    
    return "\n".join([
        f"{msg.type}: {msg.content}" 
        for msg in messages 
        if msg.type in filter_types
    ])


def build_executor_prompt(state: AgentState, step_index: int, task: str, messages_to_add: list = None) -> str:
    """构建执行器提示词
    
    Args:
        state: 当前状态
        step_index: 步骤索引
        task: 任务描述
        messages_to_add: 当前轮次新增的消息（用于合并到对话历史）
    """
    from src.prompt.prompt_loader import get_prompt
    
    previous_results = state.get("step_results", [])
    context = ""
    if previous_results:
        context = "\n".join([
            f"步骤{i+1}: {r.step_description} -> {r.output_result or '无结果'}"
            for i, r in enumerate(previous_results[-3:])  # 只显示最近3步
        ])

    # ⭐ 合并现有消息和当前轮次新增的消息
    messages = state.get("messages", []).copy()
    if messages_to_add:
        messages.extend(messages_to_add)
    
    chat_history_str = format_message_history(messages)

    # 从 YAML 加载提示词模板
    executor_prompt_template = get_prompt("plan_executor")
    
    prompt = executor_prompt_template.format(
        query=state.get('rewritten_query', ''),
        step_index=step_index + 1,
        task=task,
        context=context or '无',
        chat_history=chat_history_str or '无'
    )
    return prompt



def finalize_execution(state: AgentState) -> dict:
    """
    基于结构化 step_results 生成最终执行摘要。

    这里统一使用 `original_query` / `final_response`，不再回读历史上语义混杂的字段名。
    """
    step_results = state.get("step_results", [])
    intent = state.get("intent")
    is_sop = bool(intent and sop_loader.has_sop(intent))

    summary = PlanExecutionSummary(
        # plan_id=state.get("thread_id", "unknown"),
        query=state.get("original_query", ""),
        intent=intent,
        is_sop=is_sop,
        total_steps=len(state.get("plan", [])),
        plan_steps=state.get("plan", []),
        completed_steps=len([r for r in step_results if r.status == StepStatus.SUCCESS]),
        failed_steps=len([r for r in step_results if r.status == StepStatus.FAILED]),
        skipped_steps=len([r for r in step_results if r.status == StepStatus.SKIPPED]),
        overall_status=StepStatus.SUCCESS if all(
            r.status == StepStatus.SUCCESS for r in step_results
        ) else StepStatus.FAILED,
        final_response=state.get("final_response", "")
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

    duration_text = f"{summary.total_duration_ms:.0f}ms" if summary.total_duration_ms is not None else "未知"
    
    # 📝 添加完成消息
    status_emoji = "🎉" if summary.overall_status == StepStatus.SUCCESS else "⚠️"
    completion_message = AIMessage(
        content=f"{status_emoji} 所有步骤已完成\n" +
                f"• 总计: {summary.total_steps} 步\n" +
                f"• 成功: {summary.completed_steps} 步\n" +
                f"• 失败: {summary.failed_steps} 步\n" +
                f"• 总耗时: {duration_text}\n" +
                f"• Token消耗: {summary.total_token_usage.total_tokens}"
    )

    return {
        "execution_summary": summary,
        "messages": [completion_message]
    }


async def finalize_execution_node(state: AgentState) -> dict:
    return finalize_execution(state)


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

    query = state.get("rewritten_query", "")
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    step_results = state.get("step_results", [])
    intent = state.get("intent")
    is_sop_matched = bool(intent and sop_loader.has_sop(intent))
    
    sop_completed = False
    # 判断是否执行完计划
    if is_sop_matched and step_results:
        if current_step >= len(plan):
            sop_completed = True
            logger.info("SOP plan completed with %s steps", len(plan))
    
    # 如果还没有执行任何步骤，直接继续
    if not step_results:
        return {}
    
    # 构建已完成步骤的摘要
    completed_steps_summary = []
    for result in step_results:
        status = "✅ 成功" if result.status == StepStatus.SUCCESS else "❌ 失败"
        summary = f"{status} 步骤{result.step_index + 1}: {result.step_description}"
        if result.output_result:
            summary += f"\n   结果: {result.output_result[:150]}"
        if result.error_message:
            summary += f"\n   错误: {result.error_message[:100]}"
        completed_steps_summary.append(summary)
    
    # 剩余步骤
    remaining_steps = plan[current_step:] if current_step < len(plan) else []
    
    # ⭐ 从prompt_loader获取提示词模板
    from src.prompt.prompt_loader import get_prompt
    
    # ⭐ 组装逻辑在这里（调用方负责）
    if is_sop_matched and not sop_completed:
        # SOP执行中：使用SOP模板
        prompt_template = get_prompt("replan_sop_in_progress")
        replan_prompt = prompt_template.format(
            query=query,
            plan_list="\n".join([f"{i+1}. {step}" for i, step in enumerate(plan)]),
            completed_steps="\n".join(completed_steps_summary),
            remaining_steps="\n".join([f"{i+current_step+1}. {step}" for i, step in enumerate(remaining_steps)]) if remaining_steps else "无",
            remaining_count=len(remaining_steps)
        )
    else:
        # 非SOP或SOP已完成：使用通用模板
        prompt_template = get_prompt("replan_general")
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
        result = await get_gpt_model("gpt-4.1-mini").ainvoke(messages)
        
        # 解析LLM响应
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
                logger.debug("Replan JSON parse failed: %s", e)
        
        # 策略3: 使用 LangChain 的 JsonOutputParser 强制解析
        if not decision_data:
            try:
                parser = JsonOutputParser()
                decision_data = parser.invoke(result)
            except Exception as e:
                logger.debug("Replan JsonOutputParser failed: %s", e)
        
        # 最后的兜底: 默认继续执行
        if not decision_data:
            logger.warning("Unable to parse replan response, defaulting to continue")
            decision_data = {
                "decision": "continue",
                "reasoning": "无法解析LLM响应，默认继续执行"
            }
        decision = decision_data.get("decision", "continue")
        reasoning = decision_data.get("reasoning", "")
        
        logger.info("Replan decision=%s reasoning=%s", decision, reasoning[:120])
        
        messages_to_add = []
        
        # 根据决策返回不同的结果
        if decision == "respond":
            routing_message = AIMessage(
                content="💡 已收集足够信息，正在生成最终答案..."
            )
            messages_to_add.append(routing_message)

            return Command(goto="finalize_execution_node", update={
                "messages": messages_to_add,
                "current_step": len(plan)
            })
        
        elif decision == "replan":
            # 需要重新规划
            new_plan = decision_data.get("new_plan", [])
            
            replan_message = AIMessage(
                content="🔄 需要调整计划\n新计划:\n" +
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
            # 不添加消息，避免在对话历史中插入过时的推理内容
            pass
            
            return {
                "messages": messages_to_add
            }
    
    except Exception as e:
        logger.exception("Replan failed")
        
        # 出错时默认继续执行
        error_message = AIMessage(
            content=f"⚠️ 评估过程出错，继续执行原计划\n错误: {str(e)[:100]}"
        )
        
        return {
            "messages": [error_message]
        }
