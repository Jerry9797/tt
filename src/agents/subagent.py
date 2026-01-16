"""
通用SubAgent框架
支持配置驱动的动态任务执行

使用示例:
```python
result = await run_subagent({
    "task": "分析shopName字段的获取逻辑",
    "tools": ["grep_code", "read_java_file", "get_experiment_by_field"],
    "context": {"field_name": "shopName"}
})
```
"""

from typing import Dict, List, Optional, Any, Callable
from pydantic import BaseModel, Field
from langchain_core.tools import tool, BaseTool
from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
import asyncio


# ============================================================================
# 配置模型
# ============================================================================

class SubAgentConfig(BaseModel):
    """SubAgent配置结构"""
    task: str = Field(description="任务描述，说明SubAgent需要完成什么")
    tools: List[str] = Field(default=[], description="工具名称列表，SubAgent可以使用的工具")
    context: Optional[Dict[str, Any]] = Field(default=None, description="额外上下文信息")
    max_iterations: int = Field(default=5, description="最大迭代次数，防止无限循环")
    

# ============================================================================
# 工具注册表
# ============================================================================

# 全局工具注册表 - 用于动态加载工具
_TOOL_REGISTRY: Dict[str, BaseTool] = {}


def register_tool(tool_func: BaseTool) -> BaseTool:
    """注册工具到全局注册表"""
    _TOOL_REGISTRY[tool_func.name] = tool_func
    return tool_func


def get_tool_by_name(name: str) -> Optional[BaseTool]:
    """根据名称获取工具"""
    return _TOOL_REGISTRY.get(name)


def get_tools_by_names(names: List[str]) -> List[BaseTool]:
    """根据名称列表获取工具"""
    tools = []
    for name in names:
        tool = get_tool_by_name(name)
        if tool:
            tools.append(tool)
        else:
            print(f"[SubAgent] 警告: 工具 '{name}' 未注册")
    return tools


def list_registered_tools() -> List[str]:
    """列出所有已注册的工具名称"""
    return list(_TOOL_REGISTRY.keys())


# ============================================================================
# 通用SubAgent执行器
# ============================================================================

class GenericSubAgent:
    """
    通用SubAgent - 基于ReAct模式
    
    特点:
    - 配置驱动: 通过SubAgentConfig动态配置任务和工具
    - 自主决策: 内部使用ReAct循环自主规划执行
    - 工具隔离: 每个SubAgent只能使用指定的工具集
    """
    
    def __init__(self, llm=None):
        """
        初始化SubAgent
        
        Args:
            llm: 语言模型实例，默认使用q_max
        """
        if llm is None:
            from src.config.llm import q_max
            self.llm = q_max
        else:
            self.llm = llm
    
    def _build_system_prompt(self, config: SubAgentConfig) -> str:
        """构建系统提示词"""
        context_str = ""
        if config.context:
            context_str = "\n".join([f"- {k}: {v}" for k, v in config.context.items()])
            context_str = f"\n\n## 上下文信息\n{context_str}"
        
        return f"""你是一个专业的代码分析助手。你需要完成以下任务：

## 任务
{config.task}
{context_str}

## 要求
1. 仔细分析任务，制定执行计划
2. 使用可用的工具逐步完成任务
3. 每一步都要清晰说明你在做什么
4. 完成后给出结构化的分析结果

## 输出格式
最终结果请使用以下格式：
```
### 分析结果
- 发现: <主要发现>
- 位置: <代码位置>
- 详情: <具体细节>
- 建议: <后续建议>
```
"""
    
    async def run(self, config: SubAgentConfig) -> Dict[str, Any]:
        """
        执行SubAgent任务
        
        Args:
            config: SubAgent配置
            
        Returns:
            执行结果字典，包含:
            - success: 是否成功
            - result: 分析结果
            - iterations: 执行的迭代次数
            - error: 错误信息（如果有）
        """
        from langchain.agents import create_agent
        
        print(f"\n{'='*60}")
        print(f"[SubAgent] 启动")
        print(f"  任务: {config.task}")
        print(f"  工具: {config.tools}")
        print(f"{'='*60}\n")
        
        # 1. 动态加载工具
        tools = get_tools_by_names(config.tools)
        if not tools:
            return {
                "success": False,
                "result": None,
                "iterations": 0,
                "error": f"没有可用的工具。请求的工具: {config.tools}, 已注册: {list_registered_tools()}"
            }
        
        print(f"[SubAgent] 已加载 {len(tools)} 个工具: {[t.name for t in tools]}")
        
        # 2. 构建Agent
        system_prompt = self._build_system_prompt(config)
        
        try:
            agent = create_agent(
                system_prompt=system_prompt,
                model=self.llm,
                tools=tools,
            )
            
            # 3. 执行
            result = await agent.ainvoke({
                "messages": [HumanMessage(content=config.task)]
            })
            
            # 4. 提取结果
            output = ""
            if "messages" in result and result["messages"]:
                output = result["messages"][-1].content
            
            print(f"\n{'='*60}")
            print(f"[SubAgent] 完成")
            print(f"{'='*60}\n")
            
            return {
                "success": True,
                "result": output,
                "iterations": 1,  # create_agent 内部处理迭代
                "error": None
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "result": None,
                "iterations": 0,
                "error": str(e)
            }


# ============================================================================
# 对外暴露的工具函数
# ============================================================================

# 全局SubAgent实例
_subagent_instance: Optional[GenericSubAgent] = None


def get_subagent() -> GenericSubAgent:
    """获取全局SubAgent实例"""
    global _subagent_instance
    if _subagent_instance is None:
        _subagent_instance = GenericSubAgent()
    return _subagent_instance


@tool
async def run_subagent(config: Dict[str, Any]) -> str:
    """
    运行SubAgent执行复杂的代码分析任务。
    
    当需要进行深度代码分析、查找字段逻辑、定位AB实验配置时，调用此工具。
    
    Args:
        config: SubAgent配置字典，包含:
            - task (str): 任务描述，说明需要分析什么
            - tools (List[str]): 工具列表，可选值包括 grep_code, read_java_file, find_field_usage, get_experiment_by_field
            - context (Dict): 可选的上下文信息，如 field_name, class_name 等
            - max_iterations (int): 可选，最大迭代次数，默认5
    
    Returns:
        分析结果的字符串描述
        
    Example:
        run_subagent({
            "task": "分析shopName字段的获取逻辑，找到相关的AB实验配置",
            "tools": ["grep_code", "read_java_file", "get_experiment_by_field"],
            "context": {"field_name": "shopName"}
        })
    """
    try:
        # 解析配置
        subagent_config = SubAgentConfig(**config)
        
        # 执行
        subagent = get_subagent()
        result = await subagent.run(subagent_config)
        
        if result["success"]:
            return f"SubAgent分析完成:\n{result['result']}"
        else:
            return f"SubAgent执行失败: {result['error']}"
            
    except Exception as e:
        return f"SubAgent配置错误: {str(e)}"


# 导出
__all__ = [
    'SubAgentConfig',
    'GenericSubAgent',
    'run_subagent',
    'register_tool',
    'get_tool_by_name',
    'get_tools_by_names',
    'list_registered_tools',
]
