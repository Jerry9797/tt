"""
问题预处理
对输入的文件进行修正、关键词替换、去除停用词
"""
import json

import yaml
from langchain.agents import create_agent
from config.llm import qwenplus, QdrantVecStore, TongyiEmbedding, tongyi_intent, qwenmax, get_gpt_model
from src.graph_state import AgentState, Plan
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from src.prompt.plan import planner_prompt_template
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
    chain = query_rewrite_prompt | llm | StrOutputParser()
    ret = chain.invoke({"query": state['query']})
    print("query_rewrite_node result:", ret)
    return {"faq_query": ret}

# -------------------------node---------------------------------------

def faq_retrieve_node(state: AgentState):
    query_faq = state['faq_query']
    results = qdrant_select(query_faq, collection_name="dz_channel_faq")
    return {"faq_response": "\n".join(results)}
# -------------------------node---------------------------------------
intent_dict = {
    "play_game": "玩游戏",
    "email_querycontact": "电子邮件查询联系人",
    "alarm_set": "设置闹钟",
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
    print()
    if response.content:
        return {"intent": response.content, "is_sop_matched": True}
    return {"is_sop_matched": False}

# -------------------------node---------------------------------------
"""sop plan """
def sop_plan_node(state: AgentState):
    is_sop_matched = state['is_sop_matched']
    sop_name = state['intent']
    if is_sop_matched:
        sop_config = yaml.dump("")
        plan = sop_config.get(sop_name)
        return {"plan": plan}


# -------------------------node---------------------------------------
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser

""" 自我规划 plan """
def planning_node(state: AgentState):
    query = state['query']
    # plan_prompt = [
    #     SystemMessage(content="""
    #     你是一个规划大师，请对用户的问题根据tools进行规划。
    #     输出必须是JSON数组。
    #     """),
    #     HumanMessage(content=query)
    # ]
    # prompt = ChatPromptTemplate.from_messages(plan_prompt)

    plan_parser = JsonOutputParser(pydantic_object=Plan)
    planner_prompt = PromptTemplate(
        template=planner_prompt_template,
        input_variables=["query"],
        partial_variables={"format_instructions": plan_parser.get_format_instructions()},
    )

    chain = planner_prompt | qwenmax | JsonOutputParser()
    result = chain.invoke({"query": query, "past_steps": ""})
    return {"plan": result['steps'], "current_step": 0}

# -------------------------node---------------------------------------
""" plan executor """
def plan_executor_node(state: AgentState):
    # plan = state['plan']
    # current_step = state['current_step']
    agent = create_agent(
        model=qwenplus,
        tools=[],
        system_prompt="你是数学助手"
    )
    result = agent.invoke({"messages": ["12 和 9 的乘积是多少？"]})
    print(result)

# -------------------------node---------------------------------------
""" replan """

# -------------------------node---------------------------------------
# -------------------------node---------------------------------------
# -------------------------node---------------------------------------
# -------------------------node---------------------------------------


if __name__ == '__main__':
    state = AgentState()
    state['query'] = "我怎么看不到这个商户"
    ret = plan_executor_node(state)
    print(ret)


