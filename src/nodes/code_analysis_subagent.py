"""
代码分析SubAgent
专门处理代码逻辑分析任务

SubAgent流程：
1. 定位代码文件
2. 智能提取关键方法（减少Token）
3. 静态分析（查找明显问题）
4. LLM深度分析
5. 整理结果
"""

from typing import TypedDict, List, Optional, Dict, Any
from langgraph.graph import StateGraph, END


# ============================================================================
# SubAgent状态定义
# ============================================================================

class CodeAnalysisState(TypedDict):
    """代码分析SubAgent的状态"""
    
    # 输入参数
    class_name: str              # Java类名
    field_name: str              # 目标字段
    scene_code: Optional[str]    # 场景编码
    
    # 中间结果
    file_path: Optional[str]     # 代码文件路径
    code_content: Optional[str]  # 完整代码
    key_methods: Optional[List[str]]  # 关键方法列表
    static_issues: Optional[List[Dict]]  # 静态分析结果
    
    # 输出结果  
    analysis_result: Optional[Dict]  # 最终分析结果
    issue_type: Optional[str]        # ab_experiment / code_bug / config_error
    confidence: Optional[float]      # 置信度
    
    # 控制流
    current_step: int            # 当前步骤
    error: Optional[str]         # 错误信息


# ============================================================================
# 节点1: 定位代码
# ============================================================================

def locate_code_node(state: CodeAnalysisState) -> Dict:
    """定位代码文件"""
    class_name = state["class_name"]
    
    print(f"[CodeAnalysis] Step 1: 定位代码 {class_name}")
    
    # Mock实现 - 实际应该在项目中搜索
    # 可以用: find . -name "DistanceFetcher.java"
    file_path = f"/mock/project/src/{class_name.replace('.', '/')}.java"
    
    return {
        "file_path": file_path,
        "current_step": 1
    }


# ============================================================================
# 节点2: 智能提取关键方法
# ============================================================================

def extract_methods_node(state: CodeAnalysisState) -> Dict:
    """提取与字段相关的关键方法（减少Token消耗）"""
    file_path = state["file_path"]
    field_name = state["field_name"]
    class_name = state["class_name"]
    
    print(f"[CodeAnalysis] Step 2: 提取关键方法 (field={field_name})")
    
    # Mock代码内容
    # 实际应该读取真实文件: with open(file_path) as f: code = f.read()
    code_content = f"""
package com.dianping.vc.fetcher;

import org.springframework.stereotype.Component;
import com.dianping.vc.model.Shop;
import com.dianping.vc.model.Location;

@Component
public class {class_name.split('.')[-1]} {{
    
    public String fetch{field_name.capitalize()}(Shop shop) {{
        // 获取商户位置
        Location location = shop.getLocation();
        
        // ⚠️ BUG: 未检查location是否为null
        double distance = location.calculateDistance(userLat, userLng);
        
        return format{field_name.capitalize()}(distance);
    }}
    
    private String format{field_name.capitalize()}(double value) {{
        return String.format("%.1fkm", value);
    }}
}}
    """
    
    # 智能提取：只提取相关方法（减少Token）
    key_methods = _extract_key_methods(code_content, field_name)
    
    print(f"[CodeAnalysis] 提取了 {len(key_methods)} 个关键方法")
    
    return {
        "code_content": code_content,
        "key_methods": key_methods,
        "current_step": 2
    }


def _extract_key_methods(code: str, field_name: str) -> List[str]:
    """
    智能提取关键方法（减少80% Token消耗）
    
    策略：
    1. 方法名包含字段名
    2. 方法体中有该字段
    """
    import re
    
    # 查找方法（简化版正则）
    # 实际应该用tree-sitter或JavaParser
    method_pattern = r'(public|private|protected)\s+\w+\s+\w*' + re.escape(field_name) + r'\w*\s*\([^)]*\)\s*\{[^}]*\}'
    matches = re.findall(method_pattern, code, re.IGNORECASE | re.DOTALL)
    
    # 如果没找到，找所有fetch开头的方法
    if not matches:
        method_pattern = r'(public|private|protected)\s+\w+\s+fetch\w*\s*\([^)]*\)\s*\{[^}]*\}'
        matches = re.findall(method_pattern, code, re.DOTALL)
    
    return matches[:2]  # 最多返回2个方法


# ============================================================================
# 节点3: 静态分析
# ============================================================================

def static_analysis_node(state: CodeAnalysisState) -> Dict:
    """使用静态分析工具检查代码（免费，快速）"""
    code_content = state.get("code_content", "")
    
    print(f"[CodeAnalysis] Step 3: 静态分析")
    
    # Mock静态分析结果
    # 实际应该调用SpotBugs/PMD: subprocess.run(["spotbugs", ...])
    static_issues = []
    
    # 简单的启发式检查
    if "getLocation()" in code_content and "location." in code_content:
        # 检查是否有null检查
        if "!= null" not in code_content and "== null" not in code_content:
            static_issues.append({
                "type": "NPE_RISK",
                "severity": "HIGH",
                "line": 8,
                "message": "可能的空指针引用：调用location方法前未检查null",
                "code": "location.calculateDistance(...)"
            })
    
    print(f"[CodeAnalysis] 发现 {len(static_issues)} 个潜在问题")
    
    return {
        "static_issues": static_issues,
        "current_step": 3
    }


# ============================================================================
# 节点4: LLM深度分析
# ============================================================================

def llm_analysis_node(state: CodeAnalysisState) -> Dict:
    """使用LLM分析代码逻辑（只分析疑点，减少成本）"""
    key_methods = state.get("key_methods", [])
    static_issues = state.get("static_issues", [])
    field_name = state["field_name"]
    
    print(f"[CodeAnalysis] Step 4: LLM分析")
    
    # 如果静态分析已经发现问题，LLM只需确认和提供建议
    # 如果没有发现，LLM进行深度分析
    
    # Mock LLM分析
    # 实际应该调用: from src.config.llm import q_max
    
    if static_issues:
        # 基于静态分析结果
        issue = static_issues[0]
        analysis_result = {
            "issue_type": "code_bug",
            "confidence": 0.85,
            "code_bug": {
                "bug_type": "空指针风险",
                "bug_location": f"第{issue['line']}行",
                "bug_description": issue['message'],
                "code_snippet": issue['code'],
                "suggested_fix": f"添加null检查:\nif (location != null) {{\n    double {field_name} = location.calculate{field_name.capitalize()}(...);\n}} else {{\n    return null; // 或默认值\n}}"
            },
            "reasoning": [
                "1. 静态分析发现NPE风险",
                f"2. 代码第{issue['line']}行调用location方法",
                "3. 但未进行null检查",
                "4. 建议添加空指针保护"
            ]
        }
    else:
        # 未发现明显问题
        analysis_result = {
            "issue_type": "no_obvious_issue",
            "confidence": 0.6,
            "recommendation": "未发现明显bug，建议检查：\n1. AB实验配置\n2. 数据源问题\n3. 人工Review代码"
        }
    
    print(f"[CodeAnalysis] 分析完成: {analysis_result['issue_type']}")
    
    return {
        "analysis_result": analysis_result,
        "issue_type": analysis_result["issue_type"],
        "confidence": analysis_result.get("confidence", 0.5),
        "current_step": 4
    }


# ============================================================================
# 节点5: 结果整理
# ============================================================================

def summarize_result_node(state: CodeAnalysisState) -> Dict:
    """整理分析结果为易读格式"""
    analysis_result = state.get("analysis_result", {})
    
    print(f"[CodeAnalysis] Step 5: 整理结果")
    
    # 生成易读摘要
    summary = _generate_summary(analysis_result)
    
    # 更新结果
    updated_result = {
        **analysis_result,
        "summary": summary
    }
    
    return {
        "analysis_result": updated_result
    }


def _generate_summary(analysis: Dict) -> str:
    """生成易读的总结"""
    issue_type = analysis.get("issue_type", "unknown")
    
    if issue_type == "code_bug":
        bug = analysis.get("code_bug", {})
        return f"""🐛 发现代码BUG

类型: {bug.get('bug_type')}
位置: {bug.get('bug_location')}
描述: {bug.get('bug_description')}

建议修复:
{bug.get('suggested_fix')}

分析过程:
{chr(10).join(analysis.get('reasoning', []))}
"""
    
    elif issue_type == "ab_experiment":
        exp = analysis.get("ab_experiment", {})
        return f"""🧪 AB实验影响

实验名称: {exp.get('exp_name')}
实验负责人: {exp.get('owner')}
预期结束: {exp.get('expected_end')}

说明: {exp.get('description', '')}
"""
    
    elif issue_type == "no_obvious_issue":
        return f"""✅ 未发现明显问题

{analysis.get('recommendation', '建议人工进一步排查')}
"""
    
    else:
        return "❓ 分析未得出明确结论，建议人工排查"


# ============================================================================
# 构建SubAgent Graph
# ============================================================================

def build_code_analysis_subagent():
    """构建代码分析SubAgent"""
    
    workflow = StateGraph(CodeAnalysisState)
    
    # 添加节点
    workflow.add_node("locate_code", locate_code_node)
    workflow.add_node("extract_methods", extract_methods_node)
    workflow.add_node("static_analysis", static_analysis_node)
    workflow.add_node("llm_analysis", llm_analysis_node)
    workflow.add_node("summarize", summarize_result_node)
    
    # 定义流程
    workflow.set_entry_point("locate_code")
    workflow.add_edge("locate_code", "extract_methods")
    workflow.add_edge("extract_methods", "static_analysis")
    workflow.add_edge("static_analysis", "llm_analysis")
    workflow.add_edge("llm_analysis", "summarize")
    workflow.add_edge("summarize", END)
    
    return workflow.compile()


# ============================================================================
# 便捷调用函数
# ============================================================================

def analyze_code(
    class_name: str,
    field_name: str,
    scene_code: str = None
) -> Dict[str, Any]:
    """
    分析代码的便捷函数
    
    Args:
        class_name: Java类名
        field_name: 目标字段
        scene_code: 场景编码（可选）
    
    Returns:
        分析结果字典
    """
    print(f"\n{'='*60}")
    print(f"[SubAgent] 启动代码分析")
    print(f"  类名: {class_name}")
    print(f"  字段: {field_name}")
    print(f"{'='*60}\n")
    
    subagent = build_code_analysis_subagent()
    
    initial_state = {
        "class_name": class_name,
        "field_name": field_name,
        "scene_code": scene_code,
        "current_step": 0
    }
    
    result = subagent.invoke(initial_state)
    
    print(f"\n{'='*60}")
    print(f"[SubAgent] 分析完成")
    print(f"{'='*60}\n")
    
    return result["analysis_result"]


# 导出
__all__ = [
    'CodeAnalysisState',
    'build_code_analysis_subagent',
    'analyze_code',
]
