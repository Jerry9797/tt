import json

import yaml
import os

from langchain_core.messages import SystemMessage, HumanMessage

from src.config.llm import q_intent
from src.graph_state import AgentState

# 加载 SOP 配置
config_path = os.path.join(os.path.dirname(__file__), "../config/sop_config.yaml")

try:
    with open(config_path, 'r', encoding='utf-8') as f:
        sop_config = yaml.safe_load(f)
except Exception as e:
    print(f"Warning: Failed to load sop_config.yaml: {e}")
    sop_config = {}

# 动态生成 intent_dict 和 sop_plans
intent_dict = {key: val["name"] for key, val in sop_config.items()}
sop_plans = {key: val["steps"] for key, val in sop_config.items()}

def sop_match_node(state: AgentState):
    """意图识别，是否命中SOP"""
    faq_query = state['faq_query']
    intent_string = json.dumps(intent_dict, ensure_ascii=False)

    system_prompt = f"""You are Qwen, created by Alibaba Cloud. You are a helpful assistant. 
    You should choose one tag from the tag list:
    {intent_string}
    Just reply with the chosen tag. If none match, reply 'Other'."""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=faq_query),
    ]

    response = q_intent.invoke(messages)
    intent = response.content
    
    if intent and intent in intent_dict:
        # 命中 SOP，注入预定义计划
        plan = sop_plans.get(intent, [])
        return {
            "intent": intent, 
            "is_sop_matched": True,
            "plan": plan,
            "current_step": 0
        }
    
    return {"is_sop_matched": False}
