"""
代码分析工具
将代码分析SubAgent封装为Tool，供主Agent调用
"""

from langchain_core.tools import tool
from typing import Dict, Any


@tool
def analyze_java_code(
    class_name: str, 
    field_name: str,
    scene_code: str = ""
) -> Dict[str, Any]:
    """
    分析Java代码逻辑，查找bug或AB实验影响
    
    这是一个智能代码分析工具，可以：
    1. 定位Java类代码
    2. 智能提取关键方法（减少Token消耗）
    3. 使用静态分析工具查找明显问题
    4. 使用LLM深度分析代码逻辑
    5. 返回详细的分析报告
    
    Args:
        class_name: Java类全名，如 "DistanceFetcher" 或 "com.dianping.vc.fetcher.DistanceFetcher"
        field_name: 目标字段名，如 "distance"
        scene_code: 场景编码（可选），如 "mt_waimai_shop_list"
    
    Returns:
        分析结果字典，包含：
        - issue_type: 问题类型（code_bug/ab_experiment/config_error/no_obvious_issue）
        - confidence: 置信度 (0.0-1.0)
        - summary: 易读的摘要
        - 详细信息（根据issue_type不同）
    
    Examples:
        当distance字段缺失时：
        >>> analyze_java_code("DistanceFetcher", "distance")
        {
            "issue_type": "code_bug",
            "confidence": 0.85,
            "code_bug": {
                "bug_type": "空指针风险",
                "bug_location": "第8行",
                "suggested_fix": "添加null检查..."
            },
            "summary": "🐛 发现代码BUG\n..."
        }
    """
    from src.nodes.code_analysis_subagent import analyze_code
    
    print(f"[Tool] 调用代码分析SubAgent")
    print(f"  - class_name: {class_name}")
    print(f"  - field_name: {field_name}")
    
    # 调用SubAgent
    result = analyze_code(
        class_name=class_name,
        field_name=field_name,
        scene_code=scene_code or None
    )
    
    print(f"[Tool] SubAgent完成")
    print(f"  - issue_type: {result.get('issue_type')}")
    print(f"  - confidence: {result.get('confidence')}")
    
    return result


# 导出
__all__ = ['analyze_java_code']
