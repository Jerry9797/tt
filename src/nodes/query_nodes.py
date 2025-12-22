from typing import Literal, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command, interrupt

from src.config.llm import q_plus
from src.graph_state import AgentState

query_rewrite_prompt = ChatPromptTemplate.from_template(
    """
    # 角色定义
    你是一个【美团服务零售频道页后端问题定位专家】。
    你负责导购链路 API 层频道页的推荐列表模块（包含内容、商户、商品列表等）。
    你擅长使用查询工具记录、分析后端日志、进行代码提取和处理分析，针对线上展示 case 进行排查。

    # 任务说明
    你的任务是对用户输入的排查请求进行 Query 改写和关键词提取。

    # 上下文信息：
    {history}

    # 当前输入 Query: 
    {query}

    # 处理规则
    1. **结合业务背景补全语义**：
       - 用户输入通常与排错相关，如“它没出”应结合上下文补全为“指定的商户/商品在推荐列表中未展示”。
       - 识别专业术语：API层、猜你喜欢、商户列表、商品列表、外部调用等。
    2. **意图澄清 (慎用)**：
       - **改写优先原则**：只要输入在美团后端排错背景下能产生合理推断，就进行改写补全，不要轻易追问。
       - 只有当输入完全无法理解（如“啊吧啊吧”、纯乱码）或严重缺乏定位对象（且无历史记录）时，才设置 `need_clarification` 为 true。
    3. **Query 改写**：
       - 将口语化的排查请求转为规范的后端定位描述。
       - 补全指代对象（如“这条请求” -> “API层后端请求”）。
    4. **关键词提取**：
       - 提取核心实体名、接口名、错误代码或业务模块名。

    # Few-shot 示例
    - 用户输入：“它怎么没出” -> 改写：“[上下文推断] 为什么目标实体（商户/内容/商品）在推荐列表中没有展示？”
    - 用户输入：“查下日志” -> 改写：“查询该 case 对应调度链路的后端日志以分析定位问题。”
    - 用户输入：“外部请求返回啥” -> 改写：“获取当前 case 中外部团队接口调用的原始请求和返回报文。”
    - 用户输入：“代码逻辑有问题” -> 改写：“分析后端核心逻辑代码，查找可能导致线上展示错误的 BUG 并给出建议。”

    # 输出格式 (JSON)
    {{
        "need_clarification": true/false,
        "clarifying_question": "如需澄清，在此简短提问。否则为空。",
        "rewritten_query": "改写后的规范排查描述",
        "keywords": ["关键词1", "关键词2", ...]
    }}
    只需输出 JSON，禁止任何解释。
    """
)

def query_rewrite_node(state: AgentState):
    print("query_rewrite_node 开始运行...")
    query = state['query']
    history = state.get('messages', [])
    history_str = "\n".join([f"{msg.type}: {msg.content}" for msg in history]) if history else ""
    
    print(f"DEBUG: [query_rewrite] History length: {len(history_str)}")
    print(f"DEBUG: [query_rewrite] Current History Msg Count: {len(history)}")

    chain = query_rewrite_prompt | q_plus | JsonOutputParser()
    ret = chain.invoke({"query": query, "history": history_str})

    if ret.get("need_clarification"):
        print(f"需要澄清: {ret.get('clarifying_question')}")
        return Command(goto="ask_human", update={
            "need_clarification": ret.get("need_clarification"),
            "response": ret.get("clarifying_question"),
            "return_to": "query_rewrite_node",
            "faq_query": "",
            "keywords": []
        })

    return {
        "faq_query": ret.get("rewritten_query", query),
        "keywords": ret.get("keywords", [])
    }

def ask_human(state: AgentState):
    from langchain_core.messages import AIMessage, HumanMessage
    
    # ⭐ 获取中断上下文
    return_to = state.get("return_to", {})
    question = state.get("response")
    source_node = "query_rewrite_node"

    
    print(f"[AskHuman] 中断来源: {source_node}")
    print(f"[AskHuman] 问题: {question}")
    print(f"[AskHuman] 将返回到: {return_to}")
    
    # ⭐ 挂起执行，等待用户输入
    user_response = interrupt(question)
    
    print(f"[AskHuman] 收到用户回复: {user_response}")
    
    # ⭐ 构造消息记录
    new_messages = [
        AIMessage(content=f"⏸️ {question}"),
        HumanMessage(content=user_response)
    ]
    
    # ⭐ 统一返回：使用human_input存储用户输入
    update_dict = {
        "messages": new_messages,
        "need_clarification": False   # 清除中断状态
    }
    
    print(f"[AskHuman] 返回到节点: {return_to}")
    
    # ⭐ 返回到interrupt_context指定的节点
    return Command(
        goto=return_to,
        update=update_dict
    )
