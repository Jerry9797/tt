"""
问题预处理
对输入的文件进行修正、关键词替换、去除停用词
"""
import json
from langchain_core.messages import AIMessage, ToolMessage

import yaml
from langchain.agents import create_agent
from config.llm import qwenplus, QdrantVecStore, TongyiEmbedding, tongyi_intent, qwenmax, get_gpt_model
from src.graph_state import AgentState, Plan, Act, Response
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from src.prompt.plan import PLAN_PROMPT_V1
from src.tools import check_sensitive_merchant, check_low_star_merchant
from src.utils.qdrant_utils import client, qdrant_select

# from qdrant_client import QdrantClient

qwenplus = qwenplus()
qwenmax = qwenmax()
gpt = get_gpt_model()
# -------------------------node---------------------------------------
query_rewrite_prompt = ChatPromptTemplate.from_template(
    """
    你是一个query矫正助手，擅长纠正错别字、语法修正，注意不能破坏语义。
    query: {query}
    1.去除query中的停用词，比如：为什么
    2.英文全部改写为小写
    输出要求：直接输出改写后的结果，不需要任何解释和说明.
    """
)
# -------------------------node---------------------------------------

def query_rewrite_node(state: AgentState):
    chain = query_rewrite_prompt | qwenplus() | StrOutputParser()
    ret = chain.invoke({"query": state['query']})
    print("query_rewrite_node result:", ret)
    return {"faq_query": ret}

# -------------------------node---------------------------------------

def faq_retrieve_node(state: AgentState):
    query_faq = state['faq_query']
    results = qdrant_select(query_faq, collection_name="dz_channel_faq")
    if results:
       return {"faq_response": "\n".join(results)}
    return {}

# -------------------------node---------------------------------------
intent_dict = {
    "play_game": "玩游戏",
    "email_querycontact": "电子邮件查询联系人",
    "alarm_set": "设置闹钟",
    "shop_them_no_call": "商户没有召回"
}
"""SOP node"""
def sop_match_node(state: AgentState):
    """意图识别，是否命中SOP"""
    query = state['query']
    llm = tongyi_intent()
    intent_string = json.dumps(intent_dict, ensure_ascii=False)

    system_prompt = f"""You are Qwen, created by Alibaba Cloud. You are a helpful assistant. 
    You should choose one tag from the tag list:
    {intent_string}
    Just reply with the chosen tag."""
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': query}
    ]

    response = llm.invoke(messages)

    # response = client.chat.completions.create(
    #     model="tongyi-intent-detect-v3",
    #     messages=messages
    # )
    # print(response.choices[0].message.content)
    if response.content:
        return {"intent": response.content, "is_sop_matched": True}
    return {"is_sop_matched": False}

# -------------------------node---------------------------------------
"""sop plan """
def sop_plan_node(state: AgentState):
    """
    根据匹配的意图从SOP配置文件中加载对应的执行计划
    """
    is_sop_matched = state.get('is_sop_matched', False)
    sop_name = state.get('intent', '')
    
    if not is_sop_matched or not sop_name:
        return {}
    
    # 加载SOP配置文件
    import os
    sop_config_path = os.path.join(
        os.path.dirname(__file__),
        'config',
        'sop_config.yaml'
    )
    
    try:
        with open(sop_config_path, 'r', encoding='utf-8') as f:
            sop_config = yaml.safe_load(f)
        
        # 获取对应的SOP
        if sop_name in sop_config:
            sop = sop_config[sop_name]
            plan_steps = sop.get('steps', [])
            print(f"[SOP Plan] 匹配到SOP: {sop.get('name', sop_name)}")
            print(f"[SOP Plan] 步骤数: {len(plan_steps)}")
            return {"plan": plan_steps, "current_step": 0}
        else:
            print(f"[SOP Plan] 警告: 未找到SOP配置 '{sop_name}'")
            return {}
    
    except FileNotFoundError:
        print(f"[SOP Plan] 错误: SOP配置文件不存在: {sop_config_path}")
        return {}
    except Exception as e:
        print(f"[SOP Plan] 错误: 加载SOP配置失败: {e}")
        return {}



# -------------------------node---------------------------------------
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser

""" 自我规划 plan """
def planning_node(state: AgentState):
    query = state['query']
    
    # TODO 使用 RAG 检索相关文档
    # retrieved_docs = rag_retriever.retrieve(
    #     query=state.processed_query,
    #     top_k=3,
    #     min_confidence=0.6
    # )

    plan_parser = JsonOutputParser(pydantic_object=Plan)
    planner_prompt = PromptTemplate(
        template=PLAN_PROMPT_V1,
        input_variables=["query"],
        partial_variables={"format_instructions": plan_parser.get_format_instructions()},
    )

    chain = planner_prompt | qwenmax | plan_parser
    result = chain.invoke({"query": query})
    return {"plan": result['steps'], "current_step": 0}

# -------------------------node---------------------------------------
""" plan executor """
def plan_executor_node(state: AgentState):
    plan = state['plan']
    current_step = state['current_step']
    if current_step >= len(state['plan']):
        print(f"[PlanExecutor] All steps completed")
        return {}

    current_task = plan[current_step]

    system_prompt = f"""
    你是一个严格的计划执行节点。
    你的职责：仅执行计划中的当前步骤，不进行额外推理。
    当前步骤：{current_task}
    你被要求执行步骤 {current_step + 1}: {plan[current_step]}
    如果需要调用工具，请直接调用。不要重复前面步骤。
    用户问题：{state['query']}
    """


    agent = create_agent(
        model=qwenplus,
        tools=[check_sensitive_merchant, check_low_star_merchant],
        system_prompt=system_prompt
    )
    result = agent.invoke({"input": ""})
    return {
        "current_plan_index": current_step + 1,
        # "messages": state['messages'] + [AIMessage(content=result)],
        # "needs_human_help": needs_human or state.needs_human_help
    }

# -------------------------node---------------------------------------
""" replan """
def replan_node(state: AgentState):
    query = state['query']
    plan_list = state['plan']
    past_steps = state['past_steps']
    replanner_prompt = f"""
    你的目标是 {query} \n
    你的最初计划是 {plan_list} \n
    你目前已经完成了以下步骤 {past_steps} \n
    请相应的更新你的计划，如果不需要更多步骤并且您可以返回给用户，那么请做出响应（Response）。否则，请填写计划（Plan）。只添加仍然需要完成的步骤，不要将已完成的步骤作为计划的一部分返回。
    """
    replan_parser = JsonOutputParser(pydantic_object=Act)

    prompt = ChatPromptTemplate.from_template(replanner_prompt)
    chain = prompt | qwenmax() | replan_parser
    result = chain.invoke({"query": query, "plan_list": state['plan'], "past_steps": state['past_steps']})
    if isinstance(result.action, Response):
        return {"response": result.action.response}
    else:
        return {"plan": result.action.steps}

# -------------------------node---------------------------------------
# -------------------------node---------------------------------------
# -------------------------node---------------------------------------
# -------------------------node---------------------------------------


if __name__ == '__main__':
    state = AgentState()
    state['query'] = "我在dp端查询不到1002商户"
    state['is_sop_matched'] = True
    state['intent'] = "shop_them_no_call"
    ret = sop_plan_node(state)
    state['plan'] = ret['plan']
    state['current_step'] = 0
    state['messages'] = [HumanMessage(content="我在dp端查询不到1002商户")]
    result = plan_executor_node(state)
    print(ret)


