from langchain.agents import create_agent
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from datetime import datetime
from langgraph.errors import GraphInterrupt
import time
import traceback

from src.config.llm import q_max
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
    """生成执行计划"""
    from langchain_core.messages import AIMessage
    
    faq_query = state['faq_query']
    plan_parser = JsonOutputParser(pydantic_object=Plan)
    planner_prompt = PromptTemplate(
        template=planner_prompt_template,
        input_variables=["query"],
        partial_variables={"format_instructions": plan_parser.get_format_instructions()},
    )

    chain = planner_prompt | q_max | JsonOutputParser()
    result = chain.invoke({"query": faq_query, "past_steps": ""})
    
    steps = result.get('steps', [])
    
    # 📝 添加计划生成消息
    plan_message = AIMessage(
        content=f"📋 已生成执行计划，共{len(steps)}个步骤：\n" + 
                "\n".join([f"{i+1}. {step}" for i, step in enumerate(steps)])
    )
    
    return {
        "plan": steps,
        "current_step": 0,
        "messages": [plan_message]
    }


def plan_executor_node(state: AgentState) -> dict:
    """增强版计划执行节点 - 详细追踪每步执行结果"""
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
    
    # 📝 添加开始执行的消息
    from langchain_core.messages import AIMessage
    messages_to_add = []
    
    # 开始消息
    start_message = AIMessage(
        content=f"🔄 开始执行步骤 {current_step + 1}/{len(plan)}: {step_description}"
    )
    messages_to_add.append(start_message)

    try:
        print(f"[执行] 步骤 {current_step + 1}/{len(plan)}: {step_description}")

        # 准备Agent系统提示
        system_prompt = build_executor_prompt(state, current_step, step_description)

        # 创建Agent
        agent = create_agent(
            system_prompt=system_prompt,
            model=q_max,
            tools=[check_low_star_merchant, check_sensitive_merchant],
        )

        # 执行
        start_exec = time.time()
        execution_result = agent.invoke()
        exec_duration = (time.time() - start_exec) * 1000

        # 提取工具调用信息
        tool_calls = extract_tool_calls(execution_result)

        # 更新结果
        step_result.status = StepStatus.SUCCESS
        step_result.end_time = datetime.now()
        step_result.duration_ms = exec_duration
        step_result.agent_response = str(execution_result.get("output", ""))
        step_result.output_result = extract_output(execution_result)
        step_result.tool_calls = tool_calls

        print(f"[成功] 步骤 {current_step + 1} 完成,耗时 {exec_duration:.2f}ms")
        
        # 📝 添加成功消息
        result_summary = step_result.output_result[:200] if step_result.output_result else "执行完成"
        tools_used = f" (使用了{len(tool_calls)}个工具)" if tool_calls else ""
        
        success_message = AIMessage(
            content=f"✅ 步骤 {current_step + 1} 完成{tools_used}\n{result_summary}"
        )
        messages_to_add.append(success_message)

    except GraphInterrupt as gi:
        # 处理中断 - 需要人工干预
        step_result.status = StepStatus.NEED_CLARIFICATION
        step_result.interrupt_question = str(gi.value)
        step_result.end_time = datetime.now()
        step_result.duration_ms = (step_result.end_time - step_result.start_time).total_seconds() * 1000
        print(f"[中断] 步骤 {current_step + 1} 需要澄清: {gi.value}")
        
        # 📝 添加中断消息
        interrupt_message = AIMessage(
            content=f"⏸️ 步骤 {current_step + 1} 需要您的帮助\n{gi.value}"
        )
        messages_to_add.append(interrupt_message)
        
        # 重新抛出中断以便上层处理
        raise

    except Exception as e:
        # 处理错误
        step_result.status = StepStatus.FAILED
        step_result.error_message = str(e)
        step_result.error_traceback = traceback.format_exc()
        step_result.end_time = datetime.now()
        step_result.duration_ms = (step_result.end_time - step_result.start_time).total_seconds() * 1000
        print(f"[失败] 步骤 {current_step + 1} 执行失败: {e}")
        
        # 📝 添加失败消息
        error_message = AIMessage(
            content=f"❌ 步骤 {current_step + 1} 执行失败\n错误: {str(e)[:200]}"
        )
        messages_to_add.append(error_message)

    # 返回更新的状态
    return {
        "current_step": current_step + 1,
        "step_results": [step_result],
        "current_step_result": step_result,
        # 📝 添加消息到对话历史
        "messages": messages_to_add,
        # 保持向后兼容
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
3. 如果信息不足,说明需要什么信息
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
        plan_id=state.get("thread_id", "unknown"),
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


def replan_node(state: AgentState):
    pass
