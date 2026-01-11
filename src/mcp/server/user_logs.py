# Create an MCP server
from typing import Dict, Any

from mcp.server import FastMCP

mcp = FastMCP("ShopThemeInfo", json_response=True, port=8002)

@mcp.tool()
def get_visit_record_by_userid(user_id: str, time_range: str) -> Dict[str, Any]:
    """
    查询用户在指定时间段的访问历史记录

    **使用场景**：
    - 需要获取traceId以便进一步分析
    - 查看用户访问了哪些页面/商户
    - 用户反馈问题但未提供traceId

    Args:
        user_id: 用户ID，示例："4929259479"
        time_range: 时间范围，格式："2025-07-24 20:00 到 2025-07-24 22:00"

    Returns:
        包含访问记录的字典，每条记录包括：
        - trace_id: 链路追踪ID
        - access_time: 访问时间
        - scene_code: 场景编码
        - restored_link: 还原链接

    **示例**：
        查询用户4929259479在2025年7月24日20点到22点访问频道页时的记录
    """
    # Mock数据
    records = []

    # 示例用户 4929259479
    if user_id == "4929259479" and "2025-07-24" in time_range:
        records.append({
            "trace_id": "-4451889794465257025",
            "access_time": "2025-07-24 21:30:15",
            "scene_code": "home_feed",
            "restored_link": "http://mock-link/restore?traceId=-4451889794465257025"
        })
        records.append({
            "trace_id": "trace_example_2",
            "access_time": "2025-07-24 20:15:00",
            "scene_code": "search_result",
            "restored_link": "http://mock-link/restore?traceId=trace_example_2"
        })

    # 示例用户 1000 (响应用户请求)
    elif user_id == "1000":
        # 模拟近两天的数据
        from datetime import datetime, timedelta
        now = datetime.now()
        yesterday = now - timedelta(days=1)

        records.append({
            "trace_id": "trace_user_1000_1",
            "access_time": now.strftime("%Y-%m-%d %H:%30:%S"),
            "scene_code": "poi_detail",
            "restored_link": "http://mock-link/restore?traceId=trace_user_1000_1"
        })
        records.append({
            "trace_id": "trace_user_1000_2",
            "access_time": yesterday.strftime("%Y-%m-%d 14:%15:%S"),
            "scene_code": "home_feed",
            "restored_link": "http://mock-link/restore?traceId=trace_user_1000_2"
        })

    return {
        "user_id": user_id,
        "time_range": time_range,
        "records": records,
        "count": len(records)
    }


@mcp.tool()
def get_qpro_config_by_scene_code(scene_code: str) -> Dict[str, Any]:
    """
    根据 scene_code 查询 QPro 配置（DAG执行链）

    Args:
        scene_code: 场景编码 (e.g. "home_feed", "poi_detail")

    Returns:
        包含 Hierarchy 结构的 JSON 配置，主要由 Java 类名组成。
        结构：Abilities -> VPs -> Options
    """
    # Mock QPro Hierarchy
    return {
        "sceneCode": scene_code,
        "description": f"QPro Configuration for {scene_code}",
        "abilities": [
            {
                "abilityName": "com.meituan.qpro.ability.RecallAbility",
                "description": "召回能力",
                "vpoints": [
                    {
                        "vpName": "com.meituan.qpro.vp.MainRecallVP",
                        "options": [
                            {"class": "com.meituan.recall.BaseRecallOption", "enabled": True},
                            {"class": "com.meituan.recall.PersonalizedRecallOption", "enabled": True}
                        ]
                    }
                ]
            },
            {
                "abilityName": "com.meituan.qpro.ability.FilterAbility",
                "description": "过滤能力",
                "vpoints": [
                    {
                        "vpName": "com.meituan.qpro.vp.GeoFilterVP",
                        "options": [
                            {"class": "com.meituan.filter.DistanceFilterOption", "enabled": True},
                            {"class": "com.meituan.filter.CityFilterOption", "enabled": True}
                        ]
                    },
                    {
                        "vpName": "com.meituan.qpro.vp.RiskFilterVP",
                        "options": [
                            {"class": "com.meituan.filter.SensitiveWordOption", "enabled": True}
                        ]
                    }
                ]
            },
            {
                "abilityName": "com.meituan.qpro.ability.RankAbility",
                "description": "排序能力",
                "vpoints": [
                    {
                        "vpName": "com.meituan.qpro.vp.LTRRankVP",
                        "options": [
                            {"class": "com.meituan.rank.ClickRateModelOption", "enabled": True},
                            {"class": "com.meituan.rank.ConversionRateModelOption", "enabled": False}
                        ]
                    }
                ]
            }
        ]
    }


if __name__ == '__main__':
    """Run ShopTheme MCP Server"""
    print("Starting user log MCP Server on port 8002...")
    mcp.run(transport="streamable-http")
