"""
通用链路追踪工具库
所有诊断场景的基础工具集 - 基于TraceID
"""

from langchain_core.tools import tool
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import random


# ============================================================================
# 核心工具：TraceID相关
# ============================================================================

@tool
def get_visit_record_by_userid(
    user_id: str,
    start_time: str,
    end_time: str = None,
    platform: str = "mt"
) -> Dict[str, Any]:
    """
    ⭐ 核心工具1：根据用户ID和时间查询访问记录，获取traceId
    
    这是所有诊断的第一步！没有traceId无法继续。
    
    Args:
        user_id: 用户ID（必须）
        start_time: 访问时间起点，格式：2024-12-24 12:00:00 或 2024-12-24 12:00
        end_time: 可选，默认为start_time后1小时
        platform: mt（美团）或dp（点评），默认mt
    
    Returns:
        {
            "success": True,
            "count": 记录数,
            "records": [
                {
                    "trace_id": "trace_xxx_12345",
                    "user_id": "10086",
                    "timestamp": "2024-12-24 12:30:15",
                    "scene_code": "mt_waimai_shop_list",
                    "api_path": "/api/v1/channel/recommend"
                }
            ]
        }
    
    Tips:
        - 如果找不到记录，建议扩大时间范围（前后各1小时）
        - 可以不提供end_time，默认查询1小时内的记录
    """
    # Mock实现
    if not end_time:
        # 默认查询1小时范围
        end_time = start_time
    
    return {
        "success": True,
        "count": 1,
        "query_time_range": f"{start_time} ~ {end_time}",
        "records": [
            {
                "trace_id": f"trace_{platform}_{user_id}_{int(datetime.now().timestamp())}",
                "user_id": user_id,
                "timestamp": start_time,
                "scene_code": "mt_waimai_shop_list",
                "platform": platform,
                "api_path": "/api/v1/channel/recommend",
                "request_ip": "192.168.1.100",
                "device_type": "iOS"
            }
        ]
    }


@tool
def get_trace_context(trace_id: str) -> Dict[str, Any]:
    """
    ⭐ 核心工具2：从traceId查询完整的链路上下文
    
    这是唯一真相源！包含：
    - sceneCode（场景编码）
    - experiments（用户命中的所有实验）
    - request/response（请求和响应详情）
    - 召回链路、填充链路数据
    
    Args:
        trace_id: 链路追踪ID（从get_visit_record获取）
    
    Returns:
        包含完整链路信息的字典
    """
    # Mock实现 - 模拟真实trace查询
    return {
        "trace_id": trace_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        
        # === 场景信息 ===
        "scene_code": "mt_waimai_shop_list",
        "platform": "mt",
        "page_type": "shop_list",
        "city_id": "10",
        
        # === 用户命中的实验列表 ===
        "experiments": [
            {
                "exp_id": "exp_distance_20231215",
                "exp_name": "商户距离展示优化",
                "group_id": "B",
                "group_name": "隐藏距离组",
                "priority": 10
            },
            {
                "exp_id": "exp_rating_20231220",
                "exp_name": "评分样式优化",
                "group_id": "A",
                "group_name": "对照组",
                "priority": 20
            }
        ],
        
        # === 请求参数 ===
        "request_params": {
            "lat": "31.23",
            "lng": "121.47",
            "city_id": "10",
            "user_id": "10086",
            "scene_code": "mt_waimai_shop_list",
            "page": 1,
            "page_size": 20
        },
        
        # === 召回结果 ===
        "recall_chain": {
            "status": "success",
            "total_recalled": 50,
            "shop_ids": ["1001", "1002", "1003", "1004", "1005"],
            "opt_config": {
                "recall_strategy": "collaborative_filtering",
                "max_recall": 100,
                "filter_zero_star": True
            }
        },
        
        # === 填充结果（Document/Fetcher）===
        "theme_chain": {
            "status": "success",
            "document": "ShopThemeDocument",
            "fetcher_results": {
                "distance": None,  # ← 可能缺失
                "rating": "4.5",
                "shop_name": "测试商户",
                "business_hours": "10:00-22:00",
                "tags": ["外卖", "快餐"]
            }
        },
        
        # === 最终响应数据 ===
        "response_data": {
            "status": 200,
            "shop_count": 5,
            "shops": [
                {
                    "shop_id": "1001",
                    "shop_name": "测试商户",
                    "rating": "4.5",
                    # "distance": 缺失
                }
            ]
        }
    }


# ============================================================================
# 配置查询工具
# ============================================================================

@tool
def get_plan_id_by_scene_code(scene_code: str) -> Dict[str, Any]:
    """
    根据sceneCode查询对应的planId（配置方案ID）
    
    Args:
        scene_code: 场景编码（从trace中获取）
    
    Returns:
        {
            "scene_code": "mt_waimai_shop_list",
            "plan_id": "plan_waimai_default",
            "plan_name": "外卖默认主题"
        }
    """
    # Mock实现
    return {
        "scene_code": scene_code,
        "plan_id": f"plan_{scene_code}_default",
        "plan_name": "默认主题配置",
        "version": "v1.2.3",
        "owner": "张三"
    }


@tool
def get_document_fetcher_config(plan_id: str) -> Dict[str, Any]:
    """
    获取planId对应的Document和Fetcher配置列表
    
    Args:
        plan_id: 配置方案ID（从get_plan_id_by_scene_code获取）
    
    Returns:
        {
            "plan_id": "xxx",
            "documents": [...],
            "fetchers": [...]
        }
    """
    # Mock实现
    return {
        "plan_id": plan_id,
        "document": "ShopThemeDocument",
        "fetchers": [
            {
                "fetcher_name": "DistanceFetcher",
                "fetcher_class": "com.dianping.vc.fetcher.DistanceFetcher",
                "field_name": "distance",
                "priority": 10,
                "enable": True,
                "experiments": ["exp_distance_20231215"]
            },
            {
                "fetcher_name": "RatingFetcher",
                "fetcher_class": "com.dianping.vc.fetcher.RatingFetcher",
                "field_name": "rating",
                "priority": 20,
                "enable": True,
                "experiments": []
            },
            {
                "fetcher_name": "BusinessHoursFetcher",
                "fetcher_class": "com.dianping.vc.fetcher.BusinessHoursFetcher",
                "field_name": "business_hours",
                "priority": 30,
                "enable": True,
                "experiments": []
            }
        ]
    }


@tool
def get_experiment_detail(exp_id: str) -> Dict[str, Any]:
    """
    查询实验的详细配置
    
    Args:
        exp_id: 实验ID（从trace中获取）
    
    Returns:
        实验详情，包含各分组配置
    """
    # Mock实现
    return {
        "exp_id": exp_id,
        "exp_name": "商户距离展示优化实验",
        "description": "测试隐藏距离对CTR的影响",
        "owner": "张三",
        "team": "推荐算法组",
        "start_time": "2023-12-15",
        "expected_end": "2024-01-15",
        "status": "running",
        
        # 流量分配
        "traffic": {
            "A": 50,
            "B": 50
        },
        
        # 各分组配置
        "groups": [
            {
                "group_id": "A",
                "group_name": "对照组-展示距离",
                "description": "正常展示商户距离",
                "config": {
                    "show_distance": True,
                    "distance_unit": "km",
                    "max_distance": 10
                }
            },
            {
                "group_id": "B",
                "group_name": "实验组-隐藏距离",
                "description": "隐藏商户距离信息",
                "config": {
                    "show_distance": False,  # ← 关键配置
                    "distance_unit": "km",
                    "max_distance": 10
                }
            }
        ],
        
        # 指标
        "metrics": {
            "primary": "CTR",
            "secondary": ["转化率", "客单价"]
        }
    }


# ============================================================================
# 商户信息工具
# ============================================================================

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


# ============================================================================
# 辅助工具
# ============================================================================

@tool
def get_current_time() -> str:
    """
    获取当前时间（用于时间相关查询）
    
    Returns:
        当前时间字符串，格式：2024-12-24 12:30:00
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
def parse_user_time_description(description: str) -> str:
    """
    解析用户描述的时间为标准格式
    
    Args:
        description: 用户描述，如"今天中午12点"、"昨天下午3点"
    
    Returns:
        标准时间格式：2024-12-24 12:00:00
    
    Examples:
        - "今天中午12点" → "2024-12-24 12:00:00"
        - "昨天下午3点" → "2024-12-23 15:00:00"
    """
    # Mock实现 - 实际应该用NLP解析
    now = datetime.now()
    
    if "今天" in description or "刚才" in description:
        base_date = now
    elif "昨天" in description:
        base_date = now - timedelta(days=1)
    else:
        base_date = now
    
    # 简单时间提取
    if "中午" in description or "12" in description:
        hour = 12
    elif "下午" in description:
        hour = 15
    elif "上午" in description:
        hour = 10
    else:
        hour = now.hour
    
    result = base_date.replace(hour=hour, minute=0, second=0)
    return result.strftime("%Y-%m-%d %H:%M:%S")


# ============================================================================
# 工具集导出
# ============================================================================

CORE_TOOLS = [
    get_visit_record_by_userid,
    get_trace_context,
]

CONFIG_TOOLS = [
    get_plan_id_by_scene_code,
    get_document_fetcher_config,
    get_experiment_detail,
]

MERCHANT_TOOLS = [
    check_sensitive_merchant,
    check_low_star_merchant,
]

UTILITY_TOOLS = [
    get_current_time,
    parse_user_time_description,
]

ALL_TOOLS = CORE_TOOLS + CONFIG_TOOLS + MERCHANT_TOOLS + UTILITY_TOOLS

__all__ = [
    'get_visit_record_by_userid',
    'get_trace_context',
    'get_plan_id_by_scene_code',
    'get_document_fetcher_config',
    'get_experiment_detail',
    'check_sensitive_merchant',
    'check_low_star_merchant',
    'get_current_time',
    'parse_user_time_description',
    'CORE_TOOLS',
    'CONFIG_TOOLS',
    'MERCHANT_TOOLS',
    'UTILITY_TOOLS',
    'ALL_TOOLS',
]
