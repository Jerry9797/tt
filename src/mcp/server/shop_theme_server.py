from datetime import datetime
import random
from typing import Dict, Any

from mcp.server.fastmcp import FastMCP

# Create an MCP server
mcp = FastMCP("ShopThemeInfo", json_response=True, port=8001)


@mcp.tool()
async def check_sensitive_merchant(shop_id: str, platform_id: str = "mt") -> Dict[str, Any]:
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


@mcp.tool()
async def check_low_star_merchant(shop_id: str, platform_id: str = "mt") -> Dict[str, Any]:
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
        "is_low_star": is_low_star,
        "shop_star": shop_star,
        "star_msg": "该商户为零星商户，建议协助商户提升星级" if is_low_star else f"商户星级为{shop_star}星",
        "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@mcp.tool()
async def select_shop_state(shop_id: str, visit_date: str, platform_id: str = "mt") -> Dict[str, Any]:
    """
    检查商户在某个时间是否营业

    Args:
        shop_id: 商户ID
        visit_date: 查询日期 (e.g. 2023-10-01)
        platform_id: mt（美团）或dp（点评）

    Returns:
        {
            "shop_id": "xxx",
            "is_open": bool,
            "business_status": "营业中" or "歇业",
            "business_hours": "09:00-22:00"
        }
    """
    # Mock实现
    is_open = random.choice([True, False])

    return {
        "shop_id": shop_id,
        "visit_date": visit_date,
        "is_open": is_open,
        "business_status": "营业中" if is_open else "歇业",
        "business_hours": "09:00-22:00",
    }

@mcp.tool()
async def get_shop_category(shop_id: str, platform_id: str = "mt") -> Dict[str, Any]:
    """
    查询用户所属类目

    Args:
        shop_id: 商户ID
        platform_id: mt（美团）或dp（点评）

    Returns:
        {
            "shop_id": "xxx",
            "category_id": 123,
            "category_name": "美食",
            "parent_category_id": 10,
            "parent_category_name": "餐饮"
        }
    """
    # Mock实现
    categories = ["美食", "酒店", "休闲娱乐", "丽人", "亲子"]
    category_name = random.choice(categories)
    
    return {
        "shop_id": shop_id,
        "platform_id": platform_id,
        "category_id": random.randint(100, 999),
        "category_name": category_name,
        "parent_category_id": 10,
        "parent_category_name": "餐饮" if category_name == "美食" else "综合",
        "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


if __name__ == '__main__':
    """Run ShopTheme MCP Server"""
    print("Starting ShopTheme MCP Server on port 8001...")
    mcp.run(transport="streamable-http")
