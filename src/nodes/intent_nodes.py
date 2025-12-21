import json
from langchain_core.messages import SystemMessage, HumanMessage
from src.config.llm import q_intent
from src.graph_state import AgentState

intent_dict = {
    "shop_them_not_recall": "商户未召回",
    "shop_them_info_missing": "商户消息缺失",
    "user_access_record": "用户访问记录",
    "restore_user_scene": "还原用户现场",
}

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
    
    if response.content and response.content not in ["Other", "None"]:
        return {"intent": response.content, "is_sop_matched": True}
    return {"is_sop_matched": False}
