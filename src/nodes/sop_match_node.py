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
    rewritten_query = state['rewritten_query']
    intent_string = json.dumps(intent_dict, ensure_ascii=False, indent=2)

    system_prompt = f"""你是美团后端技术支持的意图识别专家。

# 任务
从用户查询中识别问题意图，并从以下标签列表中选择最匹配的一个：

{intent_string}

# 场景区分规则（核心）

## shop_them_no_call（商户没有召回）
**关键词**："不展示"、"没召回"、"不在列表"、"未出现"、"看不到商户"
**特征**：商户完全没有出现在推荐列表中
**示例**：
- "商户1002在列表中不展示"  → shop_them_no_call
- "888商户没有召回" → shop_them_no_call  
- "商户10023在美团没出现" → shop_them_no_call

## display_field_missing（展示字段缺失）
**关键词**："字段缺失"、"没有距离"、"缺少评分"、"营业时间不显示"
**特征**：商户在列表中，但某些具体字段（距离、评分、营业时间等）不显示
**示例**：
- "商户的距离字段没显示" → display_field_missing
- "为什么评分不见了" → display_field_missing
- "商户1002缺少营业时间信息" → display_field_missing

**判断原则**：
- 如果查询只提到"商户 + 不展示/没召回"，没有明确提及具体字段 → shop_them_no_call
- 如果查询明确提到"xx字段 + 缺失/不显示" → display_field_missing

# 输出要求
只输出匹配的标签key（如：shop_them_no_call），不要输出其他任何内容。
如果无法匹配，输出 'other'。"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=rewritten_query),
    ]

    response = await q_intent.ainvoke(messages)
    intent = response.content.strip()
    
    print(f"[SOP Match] Query: {rewritten_query[:50]}")
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

