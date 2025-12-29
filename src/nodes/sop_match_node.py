import json

from langchain_core.messages import SystemMessage, HumanMessage

from src.config.llm import q_intent
from src.graph_state import AgentState
from src.config.sop_loader import get_sop_loader

# ⭐ 使用SOPLoader加载配置
sop_loader = get_sop_loader()
intent_dict = sop_loader.get_intent_dict()

async def sop_match_node(state: AgentState):
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

    response = await q_intent.ainvoke(messages)
    intent = response.content
    
    print(f"[SOP Match] Query: {faq_query[:50]}")
    print(f"[SOP Match] Identified intent: {intent}")
    
    if intent and intent in intent_dict:
        # ⭐ 从loader获取SOP配置
        sop_config = sop_loader.get_sop(intent)
        plan = sop_config.steps if sop_config else []
        
        print(f"[SOP Match] Matched SOP: {sop_config.name if sop_config else 'Unknown'}")
        print(f"[SOP Match] Steps count: {len(plan)}")
        
        return {
            "intent": intent, 
            "is_sop_matched": True,
            "plan": plan,
            "current_step": 0
        }
    
    # ⭐ 未匹配也返回intent
    print(f"[SOP Match] No SOP matched, using default")
    return {
        "is_sop_matched": False,
        "intent": "other"
    }

