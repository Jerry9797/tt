"""
工具库统一导出
方便各个节点导入使用
"""

# 商户检查工具（已有）
from .merchant_tools import (
    check_sensitive_merchant,
    check_low_star_merchant,
)

# Trace链路工具
from .trace_tools import (
    get_visit_record_by_userid,
    get_trace_context,
    get_plan_id_by_scene_code,
    get_document_fetcher_config,
    get_experiment_detail,
    get_current_time,
    parse_user_time_description,
    CORE_TOOLS,
    CONFIG_TOOLS,
    MERCHANT_TOOLS,
    UTILITY_TOOLS,
    ALL_TOOLS as TRACE_ALL_TOOLS,
)

# ⭐ 代码分析工具（新增）
from .code_analysis_tool import (
    analyze_java_code,
)

# ⭐ 用户日志工具（新增）
from .user_log_tool import (
    search_user_access_history,
    restore_user_scene,
    analyze_recall_chain,
    parse_user_query_params,
    USER_LOG_TOOLS,
)

# 合并所有工具
ALL_TOOLS = (
    [check_sensitive_merchant, check_low_star_merchant] +
    TRACE_ALL_TOOLS +
    [analyze_java_code] +
    USER_LOG_TOOLS  # ⭐ 添加用户日志工具组
)

__all__ = [
    # 商户工具
    'check_sensitive_merchant',
    'check_low_star_merchant',
    
    # Trace工具
    'get_visit_record_by_userid',
    'get_trace_context',
    'get_plan_id_by_scene_code',
    'get_document_fetcher_config',
    'get_experiment_detail',
    'get_current_time',
    'parse_user_time_description',
    
    # 代码分析工具
    'analyze_java_code',
    
    # ⭐ 用户日志工具
    'search_user_access_history',
    'restore_user_scene',
    'analyze_recall_chain',
    'parse_user_query_params',
    'USER_LOG_TOOLS',
    
    # 工具集
    'CORE_TOOLS',
    'CONFIG_TOOLS',
    'MERCHANT_TOOLS',
    'UTILITY_TOOLS',
    'ALL_TOOLS',
]
