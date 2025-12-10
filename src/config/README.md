# SOP 配置使用说明

## 概述

SOP (Standard Operating Procedure) 标准操作流程配置用于定义针对特定问题场景的固定诊断步骤。

## 文件结构

- **配置文件**: `src/config/sop_config.yaml`
- **处理节点**: `src/node.py` 中的 `sop_plan_node()`
- **测试脚本**: `tests/test_sop_plan.py`

## YAML 配置格式

```yaml
场景key:
  name: "场景名称"
  description: "场景描述"
  steps:
    - "步骤1描述"
    - "步骤2描述"
    - "步骤3描述"
```

## 当前支持的 SOP

### 1. shop_them_no_call - 商户没有召回
针对商户在推荐列表中没有被召回的问题，包含8个诊断步骤：
1. 确认商户信息
2. 检查是否为零星商户
3. 判断零星商户并给出建议
4. 检查是否为软色情违规商户
5. 判断违规商户并给出建议
6. 查询用户访问记录
7. 分析召回链路
8. 给出诊断结论

### 2. 其他示例 SOP
- `play_game` - 玩游戏
- `email_querycontact` - 电子邮件查询联系人
- `alarm_set` - 设置闹钟

## 如何添加新的 SOP

1. 在 `src/config/sop_config.yaml` 中添加新的场景配置
2. 在 `src/node.py` 的 `intent_dict` 中添加对应的意图映射
3. 运行测试验证配置是否正确

## 使用示例

```python
from src.graph_state import AgentState
from src.node import sop_plan_node

# 创建状态
state = AgentState(
    intent="shop_them_no_call",
    is_sop_matched=True,
    # ... 其他字段
)

# 获取 SOP 计划
result = sop_plan_node(state)
plan_steps = result.get('plan', [])

for i, step in enumerate(plan_steps, 1):
    print(f"{i}. {step}")
```

## 测试

运行测试脚本：
```bash
python tests/test_sop_plan.py
```
