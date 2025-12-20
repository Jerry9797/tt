"""
问题预处理
对输入的文件进行修正、关键词替换、去除停用词
"""
import json
import yaml
from datetime import time
from langchain.agents import create_agent
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.config.llm import q_plus, q_intent, q_max
from src.graph_state import AgentState, Plan
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import PromptTemplate
# from src.prompt.plan import planner_prompt_template
from src.utils.qdrant_utils import qdrant_select
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import END


# -------------------------nodes---------------------------------------

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
    # 获取历史消息并格式化
    history = state.get('messages', [])
    history_str = "\n".join([f"{msg.type}: {msg.content}" for msg in history[:-1]]) if history else ""

    chain = query_rewrite_prompt | q_plus | JsonOutputParser()
    ret = chain.invoke({"query": state['query'], "history": history_str})

    if ret.get("need_clarification"):
        return {
            "need_clarification": ret.get("need_clarification"),
            "response": ret.get("clarifying_question"),
            "faq_query": "", # 阻断后续检索
            "keywords": []
        }

    return {
        "faq_query": ret.get("rewritten_query", state['query']),
        "keywords": ret.get("keywords", [])
    }

# ... (imports overhead)
def ask_human(state: AgentState):
    """
    此节点作为中断锚点。
    实际的问询交互发生在 API 层（Graph 暂停期间）。
    当 Graph 恢复时，意味着用户已经回答了问题，
    API 层会通过 update_state 将历史记录注入。
    这个节点本身的逻辑只需要确保状态流转正常即可。
    这里我们将 need_clarification 重置，尽管 query_rewrite 会重新评估。
    """
    return {"need_clarification": False}

# -------------------------nodes---------------------------------------

def faq_retrieve_node(state: AgentState):
    query_faq = state['faq_query']
    results = qdrant_select(query_faq, collection_name="dz_channel_faq")
    return {"faq_response": "\n".join(results.points)}

# -------------------------nodes---------------------------------------
intent_dict = {
    "shop_them_not_recall": "商户未召回",
    "shop_them_info_missing": "商户消息缺失",
    "refund_query": "查询退款",
}

def sop_match_node(state: AgentState):
    """意图识别，是否命中SOP"""
    query = state['query']
    intent_string = json.dumps(intent_dict, ensure_ascii=False)

    system_prompt = f"""You are Qwen, created by Alibaba Cloud. You are a helpful assistant. 
    You should choose one tag from the tag list:
    {intent_string}
    Just reply with the chosen tag. If none match, reply 'Other'."""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query),
    ]

    response = q_intent.invoke(messages)
    
    if response.content and response.content not in ["Other", "None"]:
        return {"intent": response.content, "is_sop_matched": True}
    return {"is_sop_matched": False}

# -------------------------nodes---------------------------------------

def planning_node(state: AgentState):
    query = state['query']
    plan_parser = JsonOutputParser(pydantic_object=Plan)
    planner_prompt = PromptTemplate(
        template="planner_prompt_template",
        input_variables=["query"],
        partial_variables={"format_instructions": plan_parser.get_format_instructions()},
    )

    chain = planner_prompt | q_max | JsonOutputParser()
    result = chain.invoke({"query": query, "past_steps": ""})
    return {"plan": result.get('steps', []), "current_step": 0}

# -------------------------nodes---------------------------------------

def plan_executor_node(state: AgentState):
    # 此处为示例占位，实际需根据 plan 执行
    return {"completed_steps": ["executed_step"]}

# -------------------------nodes---------------------------------------

def replan_node(state: AgentState):
    pass

def build_graph():
    from langgraph.graph import StateGraph
    graph = StateGraph(AgentState)
    graph.add_node("query_rewrite_node", query_rewrite_node)
    graph.add_node("ask_human", ask_human) 
    graph.add_node("faq_retrieve_node", faq_retrieve_node)
    graph.add_node("sop_match_node", sop_match_node)
    graph.add_node("planning_node", planning_node)
    graph.add_node("plan_executor_node", plan_executor_node)
    graph.add_node("replan_node", replan_node)

    # edge
    graph.set_entry_point("query_rewrite_node")

    # 是否澄清
    def route_check_clarification(state: AgentState):
        if state.get("need_clarification"):
            return "ask_human"
        return "continue"

    graph.add_conditional_edges(
        "query_rewrite_node",
        route_check_clarification,
        {
            "ask_human": "ask_human",
            "continue": "faq_retrieve_node"
        }
    )

    # 回环：用户回答后（状态已更新），流程回到重写节点重新判断
    graph.add_edge("ask_human", "query_rewrite_node")

    graph.add_edge("faq_retrieve_node", "sop_match_node")
    graph.add_edge("sop_match_node", "planning_node")
    graph.add_edge("planning_node", "plan_executor_node")
    graph.add_edge("planning_node", "replan_node")
    
    checkpointer = MemorySaver()
    # 关键修改：设置 interrupt_before
    return graph.compile(checkpointer=checkpointer, interrupt_before=["ask_human"])

if __name__ == '__main__':
    state = AgentState()
    state['query'] = "我怎么看不到这个商户"

    ret = query_rewrite_node(state)
    print(ret)

