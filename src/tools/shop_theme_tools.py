# ============================================================================
# 商户信息工具
# ============================================================================
from datetime import datetime
from random import random
from typing import Dict, Any

from langchain_core.tools import tool


@tool
def check_sensitive_merchant(shop_id: str, platform_id: str = "mt") -> Dict[str, Any]:
    """
    检查商户是否为软色情违规商户

    Args:
        shop_id: 商户ID
        platform_id: mt（美团）或dp（点评）

    Returns:
        {
            "shop_id": "xxx",
            "is_violated": bool,
            "risk_score": 0.0-1.0,
            "risk_score_v2": 0 or 1,
            "violation_status": "违规详情"
        }
    """
    # Mock实现
    risk_score = random.random()
    risk_score_v2 = random.choice([0, 1])
    is_violated = risk_score > 0.5 or risk_score_v2 == 1

    return {
        "shop_id": shop_id,
        "platform_id": platform_id,
        "is_violated": is_violated,
        "risk_score": 0.8,
        "risk_score_v2": 1,
        "violation_status": "商户头图含有软色情内容" if is_violated else "正常",
        "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


@tool
def check_low_star_merchant(shop_id: str, platform_id: str = "mt") -> Dict[str, Any]:
    """
    检查商户是否为零星商户

    Args:
        shop_id: 商户ID
        platform_id: mt（美团）或dp（点评）

    Returns:
        {
            "shop_id": "xxx",
            "is_low_star": bool,
            "shop_star": 0-5,
            "star_msg": "说明"
        }
    """
    # Mock实现
    shop_star = random.randint(0, 5)
    is_low_star = shop_star == 0

    return {
        "shop_id": shop_id,
        "platform_id": platform_id,
        "is_low_star": is_low_star,
        "shop_star": shop_star,
        "star_msg": "该商户为零星商户，建议协助商户提升星级" if is_low_star else f"商户星级为{shop_star}星",
        "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }