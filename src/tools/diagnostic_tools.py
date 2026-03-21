"""
补充诊断工具
为新增 SOP 提供最小可调用能力，当前使用结构化 Mock 返回。
"""

from datetime import datetime
from typing import Any, Dict, List

from langchain_core.tools import tool


@tool
def query_request_related_assets(trace_id: str = "", scene_code: str = "") -> Dict[str, Any]:
    """
    查询某个请求关联的类资产、配置资产和实验资产。
    """
    resolved_scene_code = scene_code or "mt_waimai_shop_list"
    resolved_trace_id = trace_id or f"trace_asset_{int(datetime.now().timestamp())}"

    assets: List[Dict[str, str]] = [
        {
            "asset_name": "ShopThemeDocument",
            "asset_type": "document",
            "identifier": "document:ShopThemeDocument",
            "reason": "trace 对应的主题文档定义",
        },
        {
            "asset_name": "DistanceFetcher",
            "asset_type": "fetcher_class",
            "identifier": "com.dianping.vc.fetcher.DistanceFetcher",
            "reason": "负责填充 distance 字段",
        },
        {
            "asset_name": "exp_distance_20231215",
            "asset_type": "experiment",
            "identifier": "exp_distance_20231215",
            "reason": "trace 中命中的距离展示实验",
        },
        {
            "asset_name": f"plan_{resolved_scene_code}_default",
            "asset_type": "plan_config",
            "identifier": f"plan:{resolved_scene_code}",
            "reason": "当前 scene_code 对应的 plan 配置",
        },
    ]

    return {
        "trace_id": resolved_trace_id,
        "scene_code": resolved_scene_code,
        "asset_count": len(assets),
        "assets": assets,
        "dependency_summary": [
            "scene_code -> plan_config -> document/fetcher",
            "trace -> experiments -> conditional config",
        ],
    }


@tool
def query_merchant_exposure(
    shop_id: str,
    start_time: str,
    end_time: str,
    platform: str = "mt",
    metric: str = "exposure",
) -> Dict[str, Any]:
    """
    查询商户在指定时间范围内的曝光数据。
    """
    if metric != "exposure":
        normalized_metric = metric
    else:
        normalized_metric = "exposure"

    exposure_value = max(len(shop_id) * 123, 100)

    return {
        "shop_id": shop_id,
        "platform": platform,
        "metric": normalized_metric,
        "start_time": start_time,
        "end_time": end_time,
        "value": exposure_value,
        "unit": "count",
        "query_status": "success",
        "notes": "当前为Mock实现，后续可替换为真实曝光查询服务。",
    }


@tool
def query_rule_engine_config(
    scene_code: str,
    rule_key: str = "",
    trace_id: str = "",
) -> Dict[str, Any]:
    """
    查询规则引擎配置、开关和命中条件。
    """
    resolved_rule_key = rule_key or "default_rule_chain"

    return {
        "trace_id": trace_id,
        "scene_code": scene_code,
        "rule_key": resolved_rule_key,
        "config_status": "loaded",
        "rules": [
            {
                "rule_name": "distance_display_rule",
                "enabled": True,
                "condition": "lat/lng exists and show_distance switch is on",
                "source": "rule_engine",
            },
            {
                "rule_name": "merchant_filter_rule",
                "enabled": True,
                "condition": "merchant passes zero-star and risk filtering",
                "source": "rule_engine",
            },
        ],
        "switches": [
            {"switch_name": "show_distance", "value": True},
            {"switch_name": "enable_rule_engine", "value": True},
        ],
        "summary": "规则配置已加载，可继续结合 trace 和代码实现判断是否为配置问题。",
    }


__all__ = [
    "query_request_related_assets",
    "query_merchant_exposure",
    "query_rule_engine_config",
]
