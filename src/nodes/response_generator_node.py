"""
答案生成节点 (Response Generator Node)

职责：
- 聚合所有步骤执行结果
- 提取关键发现
- 使用专门提示词生成结构化答案
- 添加必要的上下文和建议
"""
import logging

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate

from src.config.llm import get_gpt_model, mt_llm
from src.graph_state import AgentState
from src.prompt.prompt_loader import get_prompt

logger = logging.getLogger(__name__)


async def response_generator_node(state: AgentState) -> dict:
    """
    答案生成节点 - 聚合执行结果并生成最终答案
    
    Args:
        state: 包含执行结果的图状态
        
    Returns:
        包含最终答案和消息的字典
    """
    payload = build_response_generation_payload(state)
    logger.info(
        "Generating final response with %s completed steps",
        len(state.get("step_results", [])),
    )
    
    # 使用专门的提示词生成答案
    response_prompt = ChatPromptTemplate.from_template(
        get_prompt("response_generation")
    )
    
    # chain = response_prompt | get_claude_model(model="claude-haiku-4-5",streaming=True)
    chain = response_prompt | get_gpt_model(model="gpt-4.1",streaming=True)
    result = await chain.ainvoke(payload)
    
    final_response = result.content
    
    # 添加消息到对话历史
    response_message = AIMessage(
        content=f"✅ 最终答案\n\n{final_response}"
    )
    
    return {
        "final_response": final_response,
        "messages": [response_message]
    }


def build_response_generation_payload(state: AgentState) -> dict:
    query = state.get("original_query") or state.get("rewritten_query", "")
    intent = state.get("intent", "未知")
    step_results = state.get("step_results", [])

    return {
        "query": query,
        "intent": intent,
        "steps_summary": build_steps_summary(step_results),
        "tool_results": extract_tool_results(step_results),
    }


def build_steps_summary(step_results: list) -> str:
    """
    构建步骤执行摘要
    
    Args:
        step_results: 步骤执行结果列表
        
    Returns:
        格式化的步骤摘要字符串
    """
    if not step_results:
        return "未执行任何步骤"
    
    summary_lines = []
    for i, result in enumerate(step_results, 1):
        # 根据状态选择 emoji
        status_emoji = "✅" if result.status == "success" else "❌"
        
        # 提取输出结果（截取前200字符）
        output_preview = ""
        if hasattr(result, 'output_result') and result.output_result:
            output_preview = result.output_result[:200]
            if len(result.output_result) > 200:
                output_preview += "..."
        else:
            output_preview = "无结果输出"
        
        # 组装摘要行
        summary_lines.append(
            f"{i}. {status_emoji} **{result.step_description}**\n"
            f"   结果: {output_preview}"
        )
    
    return "\n\n".join(summary_lines)


def extract_tool_results(step_results: list) -> str:
    """
    提取关键工具调用结果
    
    Args:
        step_results: 步骤执行结果列表
        
    Returns:
        格式化的工具调用结果字符串
    """
    tool_calls_summary = []
    
    for i, result in enumerate(step_results, 1):
        # 提取 agent_response（包含工具调用信息）
        if hasattr(result, 'agent_response') and result.agent_response:
            # 截取前300字符作为关键信息
            response_preview = result.agent_response[:300]
            if len(result.agent_response) > 300:
                response_preview += "..."
            
            tool_calls_summary.append(
                f"**步骤 {i}**: {response_preview}"
            )
    
    if not tool_calls_summary:
        return "无工具调用结果"
    
    return "\n\n".join(tool_calls_summary)
