# 商户检查工具使用指南

## 工具列表

### 1. check_sensitive_merchant (软色情商户检查)

**功能**：查询商户是否为软色情违规商户

**参数**：
- `shop_id`: 商户ID (字符串)
- `platform_id`: 平台ID (字符串)
  - `"mt"` - 美团
  - `"dp"` - 点评

**返回值**：
```python
{
    "shop_id": "100001",
    "platform_id": "mt",
    "is_violated": True,          # 是否违规
    "risk_score": 0.78,            # 正式环境风险系数 (>0.5 为违规)
    "risk_score_v2": 1,            # 实验环境风险系数 (1 为违规)
    "violation_status": "商户头图含有软色情内容",
    "shop_msg": "该商户因'商户头图含有软色情内容'被判定为软色情违规商户"
}
```

### 2. check_low_star_merchant (低星商户检查)

**功能**：查询商户是否为低星（零星）商户

**参数**：
- `shop_id`: 商户ID (字符串)
- `platform_id`: 平台ID (字符串)
  - `"mt"` - 美团
  - `"dp"` - 点评

**返回值**：
```python
{
    "shop_id": "200001",
    "platform_id": "dp",
    "is_low_star": True,           # 是否为低星商户 (shop_star == 0)
    "shop_star": 0,                # 商户星级 (0-5)
    "star_msg": "该商户为零星商户，建议协助商户提升星级"
}
```

## 使用方式

### 方式1: 作为 LangChain Tool 使用

```python
from src.tools import check_sensitive_merchant, check_low_star_merchant

# 这些是 LangChain @tool 装饰的函数
# 可以直接传给 Agent 使用

tools = [check_sensitive_merchant, check_low_star_merchant]
agent = create_agent(model=llm, tools=tools)
```

### 方式2: 直接调用

```python
from src.tools.merchant_tools import check_sensitive_merchant, check_low_star_merchant

# 软色情检查
result1 = check_sensitive_merchant.invoke({
    "shop_id": "100001",
    "platform_id": "mt"
})
print(result1)

# 低星商户检查
result2 = check_low_star_merchant.invoke({
    "shop_id": "200001",
    "platform_id": "dp"
})
print(result2)
```

## 注意事项

⚠️ **当前版本为 Mock 版本**
- 使用随机函数生成模拟数据
- 每次调用结果会有所不同
- 仅用于开发和测试

## 测试

运行测试示例：
```bash
python src/tools/merchant_tools.py
```
