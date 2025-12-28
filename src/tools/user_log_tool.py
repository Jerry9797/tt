"""
用户日志分析工具
提供用户访问历史查询、现场还原和召回链路分析功能 (Mock版本)
"""
from typing import Dict, Any, List
from langchain_core.tools import tool

@tool
def search_user_access_history(user_id: str, time_range: str) -> Dict[str, Any]:
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

@tool
def restore_user_scene(trace_id: str) -> Dict[str, Any]:
    """
    根据traceId还原用户当时看到的内容和操作

    **使用场景**：
    - 用户反馈看到了某个商户，需要确认位置
    - 分析用户点击了什么
    - 还原现场展示

    Args:
        trace_id: 链路追踪ID

    Returns:
        包含现场还原信息的字典：
        - display_info: 展示信息
        - click_records: 点击记录
        - merchants: 展示的商户列表
    """
    # Mock数据
    if trace_id == "-4451889794465257025" or trace_id == "trace_example_2":
         return {
            "trace_id": trace_id,
            "display_info": {
                "page": "首页推荐",
                "timestamp": "2025-07-24 21:30:15",
                "device": "iPhone 14 Pro"
            },
            "merchants": [
                {"shop_id": "10001", "name": "海底捞", "position": 1},
                {"shop_id": "10002", "name": "星巴克", "position": 2},
                 {"shop_id": "10003", "name": "麦当劳", "position": 3}
            ],
            "click_records": [
                {"shop_id": "10002", "click_time": "2025-07-24 21:30:20", "action": "click_detail"}
            ]
        }
    
    elif trace_id.startswith("trace_user_1000"):
        return {
            "trace_id": trace_id,
            "display_info": {
                "page": "商户详情页" if "1" in trace_id else "首页推荐",
                "timestamp": "2025-12-27",
                "device": "Android"
            },
            "merchants": [
                {"shop_id": "20001", "name": "肯德基", "position": 1},
            ],
            "click_records": []
        }
    
    return {"trace_id": trace_id, "error": "Trace ID not found"}

@tool
def analyze_recall_chain(trace_id: str, merchant_id: str = None) -> Dict[str, Any]:
    """
    分析召回链路中的问题，定位商户未召回的原因

    **使用场景**：
    - 用户询问为何没看到某个商户
    - 诊断召回缺失问题

    Args:
        trace_id: 链路追踪ID
        merchant_id: (可选) 特定商户ID

    Returns:
        包含诊断报告的字典：
        - root_cause: 根本原因
        - detailed_reason: 详细原因
        - suggestion: 解决建议
    """
    # Mock数据
    if trace_id == "-4451889794465257025":
        return {
            "trace_id": trace_id,
            "merchant_id": merchant_id,
            "root_cause": "经纬度缺失",
            "detailed_reason": "请求参数中缺少必要的经纬度信息(lat/lng)，导致LBS召回策略失效",
            "suggestion": "请检查客户端定位权限或SDK上报逻辑"
        }
    
    return {
        "trace_id": trace_id,
        "status": "normal", 
        "msg": "Recall chain is normal"
    }

@tool
def parse_user_query_params(query: str) -> Dict[str, str]:
    """
    从自然语言查询中提取结构化参数（辅助工具）

    **使用场景**：
    - 当Agent无法直接确定参数时，可调用此工具辅助提取
    - 提取user_id和时间范围

    Args:
        query: 用户输入的自然语言查询

    Returns:
        提取的参数字典
    """
    # 简单的模拟提取，实际场景可能需要更复杂的NLP或正则
    # 这里为了演示，针对特定case做mock
    if "4929259479" in query:
        return {
            "user_id": "4929259479",
            "time_range": "2025-07-24 20:00-22:00" 
        }
    return {"error": "Could not parse parameters"}

# 工具分组
USER_LOG_TOOLS = [
    search_user_access_history,
    restore_user_scene,
    analyze_recall_chain,
    parse_user_query_params
]

if __name__ == "__main__":
    print("=" * 50)
    print("测试 User Log Tools (Mock)")
    print("=" * 50)
    
    # 测试 search_user_access_history
    print("\n1. 测试 search_user_access_history:")
    res1 = search_user_access_history.invoke({
        "user_id": "4929259479",
        "time_range": "2025-07-24 20:00-22:00"
    })
    print(res1)
    
    # 测试 restore_user_scene
    print("\n2. 测试 restore_user_scene:")
    res2 = restore_user_scene.invoke({"trace_id": "-4451889794465257025"})
    print(res2)
    
    # 测试 analyze_recall_chain
    print("\n3. 测试 analyze_recall_chain:")
    res3 = analyze_recall_chain.invoke({"trace_id": "-4451889794465257025"})
    print(res3)
    
    # 测试 parse_user_query_params
    print("\n4. 测试 parse_user_query_params:")
    res4 = parse_user_query_params.invoke({"query": "查询用户4929259479在7月24日的记录"})
    print(res4)
