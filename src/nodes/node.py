"""
问题预处理
对输入的文件进行修正、关键词替换、去除停用词
"""
import json
import yaml
from langgraph.checkpoint.memory import MemorySaver

from src.config.llm import q_plus, q_intent, q_max
from src.graph_state import AgentState, Plan
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import PromptTemplate
from src.utils.qdrant_utils import qdrant_select
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import END


# -------------------------nodes---------------------------------------

query_rewrite_prompt = ChatPromptTemplate.from_template(
    """
    你是一个 Query 预处理专家。你的任务是对用户的输入进行改写、关键词提取，并在意图不明确时进行追问。

    上下文信息：
    {history}

    当前输入 Query: {query}

    任务清单：
    1. **结合上下文理解意图**：如果当前 Query 依赖上下文（如“它也是吗”、“那个多少钱”），请结合历史信息补全语义。
    2. **意图澄清**：如果结合上下文后意图依然**极度不明确**（例如用户仅输入一个毫无背景的词，如“你好”、“在吗”且无上下文，或者指代不明无法解析），请生成一个澄清问题来询问用户意图。
       - 如果需要澄清，设置 `need_clarification` 为 true，并在 `clarifying_question` 中填写问题。
       - 如果不需要澄清，设置 `need_clarification` 为 false，`clarifying_question` 为空字符串，并继续执行改写任务。
    3. **错别字纠正**：发现并修正输入中的错别字。
    4. **语气词移除**：去掉无语义的语气词。
    5. **停用词移除**：去掉无贡献的停用词。
    6. **关键词提取**：提取核心名词或动宾短语。

    输出格式必须为 JSON：
    {{
        "need_clarification": true/false,
        "clarifying_question": "如需澄清，在此填写问题",
        "rewritten_query": "改写后的 query (如需澄清，此项可为空)",
        "keywords": ["关键词1", "关键词2", ...]
    }}
    直接输出 JSON 结果，不需要任何解释。
    """
)

def query_rewrite_node(state: AgentState):
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

# ... (other nodes)

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

