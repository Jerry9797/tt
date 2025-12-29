"""
执行结果数据模型
用于追踪plan每个步骤的执行状态、结果、耗时等信息
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class StepStatus(str, Enum):
    """步骤执行状态"""
    PENDING = "pending"          # 待执行
    RUNNING = "running"          # 执行中
    SUCCESS = "success"          # 成功
    FAILED = "failed"            # 失败
    SKIPPED = "skipped"          # 跳过
    NEED_CLARIFICATION = "need_clarification"  # 需要澄清


class ToolCall(BaseModel):
    """工具调用记录"""
    tool_name: str = Field(description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")
    result: Optional[Any] = Field(default=None, description="工具返回结果")
    error: Optional[str] = Field(default=None, description="工具执行错误")
    duration_ms: Optional[float] = Field(default=None, description="工具执行耗时(毫秒)")
    
    class Config:
        arbitrary_types_allowed = True


class StepExecutionResult(BaseModel):
    """单步执行结果"""
    # 基本信息
    step_index: int = Field(description="步骤索引,从0开始")
    step_description: str = Field(description="步骤描述")
    
    # 执行状态
    status: StepStatus = Field(default=StepStatus.PENDING, description="执行状态")
    
    # 时间信息
    start_time: Optional[datetime] = Field(default=None, description="开始时间")
    end_time: Optional[datetime] = Field(default=None, description="结束时间")
    duration_ms: Optional[float] = Field(default=None, description="执行耗时(毫秒)")
    
    # 执行详情
    input_context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="执行输入上下文")
    output_result: Optional[str] = Field(default=None, description="执行输出结果")
    agent_response: Optional[str] = Field(default=None, description="Agent响应内容")
    
    # 工具调用记录
    tool_calls: List[ToolCall] = Field(default_factory=list, description="工具调用列表")
    
    # 错误处理
    error_message: Optional[str] = Field(default=None, description="错误信息")
    error_traceback: Optional[str] = Field(default=None, description="错误堆栈")
    retry_count: int = Field(default=0, description="重试次数")
    
    # 中断处理
    interrupt_question: Optional[str] = Field(default=None, description="中断问题")
    human_response: Optional[str] = Field(default=None, description="人工回复")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="其他元数据")
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class TokenUsage(BaseModel):
    """Token消耗统计"""
    prompt_tokens: int = Field(default=0, description="Input tokens")
    completion_tokens: int = Field(default=0, description="Output tokens")
    total_tokens: int = Field(default=0, description="Total tokens")
    
    def add(self, other: "TokenUsage"):
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens


class StepExecutionResult(BaseModel):
    """单步执行结果"""
    # 基本信息
    step_index: int = Field(description="步骤索引,从0开始")
    step_description: str = Field(description="步骤描述")
    
    # 执行状态
    status: StepStatus = Field(default=StepStatus.PENDING, description="执行状态")
    
    # 时间信息
    start_time: Optional[datetime] = Field(default=None, description="开始时间")
    end_time: Optional[datetime] = Field(default=None, description="结束时间")
    duration_ms: Optional[float] = Field(default=None, description="执行耗时(毫秒)")
    
    # 资源消耗
    token_usage: Optional[TokenUsage] = Field(default_factory=TokenUsage, description="Token消耗")
    
    # 执行详情
    input_context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="执行输入上下文")
    output_result: Optional[str] = Field(default=None, description="执行输出结果")
    agent_response: Optional[str] = Field(default=None, description="Agent响应内容")
    
    # 工具调用记录
    tool_calls: List[ToolCall] = Field(default_factory=list, description="工具调用列表")
    
    # 错误处理
    error_message: Optional[str] = Field(default=None, description="错误信息")
    error_traceback: Optional[str] = Field(default=None, description="错误堆栈")
    retry_count: int = Field(default=0, description="重试次数")
    
    # 中断处理
    interrupt_question: Optional[str] = Field(default=None, description="中断问题")
    human_response: Optional[str] = Field(default=None, description="人工回复")
    
    # 元数据
    metadata: Dict[str, Any] = Field(default_factory=dict, description="其他元数据")
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class PlanExecutionSummary(BaseModel):
    """整体执行摘要"""
    plan_id: str = Field(description="计划唯一标识")
    query: str = Field(description="用户查询")
    intent: Optional[str] = Field(default=None, description="识别的意图")
    is_sop: bool = Field(default=False, description="是否为SOP流程")
    
    # 计划信息
    total_steps: int = Field(description="总步骤数")
    plan_steps: List[str] = Field(default_factory=list, description="计划步骤列表")
    
    # 执行统计
    completed_steps: int = Field(default=0, description="已完成步骤数")
    failed_steps: int = Field(default=0, description="失败步骤数")
    skipped_steps: int = Field(default=0, description="跳过步骤数")
    
    # 时间统计
    start_time: Optional[datetime] = Field(default=None, description="开始时间")
    end_time: Optional[datetime] = Field(default=None, description="结束时间")
    total_duration_ms: Optional[float] = Field(default=None, description="总耗时(毫秒)")
    
    # 资源消耗
    total_token_usage: Optional[TokenUsage] = Field(default_factory=TokenUsage, description="总Token消耗")
    
    # 整体状态
    overall_status: StepStatus = Field(default=StepStatus.PENDING, description="整体状态")
    final_response: Optional[str] = Field(default=None, description="最终响应")
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
