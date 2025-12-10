"""
商户检查工具
提供软色情商户和低星商户检查功能（Mock版本）
"""
import random
from typing import Dict, Any
from langchain_core.tools import tool


@tool
def check_sensitive_merchant(shop_id: str, platform_id: str) -> Dict[str, Any]:
    """
    查询商户是否为软色情违规商户
    
    Args:
        shop_id: 商户ID
        platform_id: 平台ID，mt表示美团，dp表示点评
        
    Returns:
        包含商户违规信息的字典，包括：
        - is_violated: 是否违规（bool）
        - risk_score: 正式环境风险系数（0-1之间的浮点数，>0.5为违规）
        - risk_score_v2: 实验环境风险系数（0或1，1为违规）
        - violation_status: 违规详情
        - shop_msg: 违规原因说明
    """
    # Mock数据：随机生成风险系数
    risk_score = random.random()
    risk_score_v2 = random.choice([0, 1])
    
    is_violated = risk_score > 0.5 or risk_score_v2 == 1
    
    violation_status = ""
    shop_msg = ""
    
    if is_violated:
        violations = [
            "商户头图含有软色情内容",
            "商户名称包含敏感词汇",
            "商户介绍存在擦边球描述",
            "用户投诉商户涉及软色情服务"
        ]
        violation_status = random.choice(violations)
        shop_msg = f"该商户因'{violation_status}'被判定为软色情违规商户"
    else:
        shop_msg = "该商户未发现软色情违规行为"
    
    result = {
        "shop_id": shop_id,
        "platform_id": platform_id,
        "is_violated": is_violated,
        "risk_score": round(risk_score, 2),
        "risk_score_v2": risk_score_v2,
        "violation_status": violation_status,
        "shop_msg": shop_msg
    }
    
    return result


@tool
def check_low_star_merchant(shop_id: str, platform_id: str) -> Dict[str, Any]:
    """
    查询商户是否为低星（零星）商户
    
    Args:
        shop_id: 商户ID
        platform_id: 平台ID，mt表示美团，dp表示点评
        
    Returns:
        包含商户星级信息的字典，包括：
        - is_low_star: 是否为低星商户（shop_star=0）
        - shop_star: 商户星级（0-5）
        - star_msg: 星级说明
    """
    # Mock数据：随机生成商户星级（0-5）
    shop_star = random.randint(0, 5)
    
    is_low_star = shop_star == 0
    
    star_msg = ""
    if is_low_star:
        star_msg = "该商户为零星商户，建议协助商户提升星级"
    else:
        star_msg = f"该商户星级为{shop_star}星"
    
    result = {
        "shop_id": shop_id,
        "platform_id": platform_id,
        "is_low_star": is_low_star,
        "shop_star": shop_star,
        "star_msg": star_msg
    }
    
    return result


# 非LangChain tool版本（如果需要直接调用）
def check_sensitive_merchant_raw(shop_id: str, platform_id: str) -> Dict[str, Any]:
    """原始版本的软色情检查函数"""
    return check_sensitive_merchant.invoke({"shop_id": shop_id, "platform_id": platform_id})


def check_low_star_merchant_raw(shop_id: str, platform_id: str) -> Dict[str, Any]:
    """原始版本的低星商户检查函数"""
    return check_low_star_merchant.invoke({"shop_id": shop_id, "platform_id": platform_id})


if __name__ == "__main__":
    # 测试示例
    print("=" * 80)
    print("测试软色情商户检查")
    print("=" * 80)
    
    for i in range(3):
        result = check_sensitive_merchant.invoke({
            "shop_id": f"10{i:04d}",
            "platform_id": "mt"
        })
        print(f"\n商户 {result['shop_id']}:")
        print(f"  违规状态: {'违规' if result['is_violated'] else '正常'}")
        print(f"  风险系数(正式): {result['risk_score']}")
        print(f"  风险系数(实验): {result['risk_score_v2']}")
        print(f"  说明: {result['shop_msg']}")
    
    print("\n" + "=" * 80)
    print("测试低星商户检查")
    print("=" * 80)
    
    for i in range(3):
        result = check_low_star_merchant.invoke({
            "shop_id": f"20{i:04d}",
            "platform_id": "dp"
        })
        print(f"\n商户 {result['shop_id']}:")
        print(f"  低星状态: {'是' if result['is_low_star'] else '否'}")
        print(f"  星级: {result['shop_star']}星")
        print(f"  说明: {result['star_msg']}")
