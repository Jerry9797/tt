import asyncio
from langgraph.types import Command, interrupt
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain.agents import create_agent

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from datetime import datetime
import time

from src.config.llm import get_gpt_model
from src.graph_state import AgentState, Plan
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

    rewritten_query = state['rewritten_query']
    intent = state.get('intent', 'default')
    
    # ⭐ 从SOPLoader获取planning prompt
    sop_loader = get_sop_loader()
    plan_prompt = sop_loader.get_planning_prompt(intent)

    plan_parser = JsonOutputParser(pydantic_object=Plan)
    format_instructions = plan_parser.get_format_instructions()

    from src.prompt.prompt_loader import get_prompt
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=get_prompt("system_prompt")),
        SystemMessage(content=plan_prompt) if plan_prompt else "",
        HumanMessage(content=rewritten_query),
        SystemMessage(content=f"所有回复必须遵循以下格式：\n{format_instructions}"),
    ])
    chain = prompt | get_gpt_model("gpt-4.1").bind_tools(ALL_TOOLS) | JsonOutputParser()
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
        start_time=datetime.now()
    )

    
    # Added for new logic
    messages_to_add = []
    
    # ⭐ 使用 state 字段判断是否处于中断恢复状态（更可靠）
    user_input = None
    is_resuming = state.get("need_clarification", False)
    
    if is_resuming:
        # 处于中断状态，查找用户的回复
        messages = state.get("messages", [])
        
        # 从后往前找最近的 HumanMessage
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, HumanMessage):
                user_input = msg.content
                print(f"[Executor] 检测到用户回复（恢复模式）: {user_input}")
                break
        
        if user_input:
            # 添加恢复消息
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
    
    print(f"[执行] 步骤 {current_step + 1}/{len(plan)}: {step_description}")
    
    # 准备Agent系统提示（传递当前轮次的新消息）
    system_prompt = build_executor_prompt(state, current_step, step_description, messages_to_add)
    
    # ⭐ 获取 MCP 工具并合并
    from src.mcp import get_mcp_manager

    mcp_manager = get_mcp_manager()
    mcp_tools = mcp_manager.get_all_tools()

    print(f"[MCP] 已加载 {len(mcp_tools)} 个 MCP 工具")

    # 合并静态工具和 MCP 工具
    all_tools = ALL_TOOLS + mcp_tools

    # 创建Agent
    agent = create_agent(
        system_prompt=system_prompt,
        # 本地环境的 openai-proxy token 已失效，执行节点优先走已验证可用的通义模型。
        model=get_gpt_model(),
        tools=all_tools,  # ⭐ 使用合并后的工具列表
    )
    
    # 执行（异步）
    start_exec = time.time()
    # ⭐ 构建输入消息：如果有用户回复，需要在当前轮次中传递给 Agent
    # 虽然 system_prompt 包含历史，但 Agent 需要在 messages 参数中接收当前用户输入
    input_messages = []
    if user_input:
        input_messages.append(HumanMessage(content=user_input))
    
    execution_result = await agent.ainvoke({"messages": input_messages})

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
        # step_result.status = StepStatus.NEED_CLARIFICATION
        # step_result.interrupt_question = question
        # step_result.end_time = datetime.now()
        # step_result.duration_ms = exec_duration
        
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
    
    # 🔍 调试输出
    print(f"\n[DEBUG] build_executor_prompt 调试信息:")
    print(f"  原始消息数: {len(state.get('messages', []))}")
    print(f"  新增消息数: {len(messages_to_add) if messages_to_add else 0}")
    print(f"  合并后总数: {len(messages)}")
    print(f"  对话历史:\n{chat_history_str if chat_history_str else '(无)'}")

    # 从 YAML 加载提示词模板
    executor_prompt_template = get_prompt("plan_executor")
    
    prompt = executor_prompt_template.format(
        query=state.get('rewritten_query', ''),
        step_index=step_index + 1,
        task=task,
        context=context or '无',
        chat_history=chat_history_str or '无'
    )
    
    # 🔍 打印完整的 system_prompt
    print(f"\n[DEBUG] System Prompt:\n{prompt}\n")
    
    return prompt



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

    query = state.get("rewritten_query", "")
    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    step_results = state.get("step_results", [])
    is_sop_matched = state.get("is_sop_matched", False)
    
    sop_completed = False
    # 判断是否执行完计划
    if is_sop_matched and step_results:
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
        result = await get_gpt_model().ainvoke(messages)
        
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
            # 不再直接生成答案，路由到专门的答案生成节点
            routing_message = AIMessage(
                content="💡 已收集足够信息，正在生成最终答案..."
            )
            messages_to_add.append(routing_message)
            
            return Command(goto="response_generator", update={
                "messages": messages_to_add,
                # 标记为完成，停止继续执行计划
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
