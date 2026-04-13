---
name: 商户未召回
description: |
  商户在推荐列表中没有被召回的问题诊断流程
---

# 商户未召回

> 商户在推荐列表中没有被召回的问题诊断流程

## 歧义消除规则

**调用本 Skill 的条件**：用户描述的是"商户整体不出现在列表中"，没有提到具体缺失字段。
- 触发：「不展示」「没召回」「不在列表」「未出现」「看不到商户」
- 不触发：如果用户明确提到某个字段缺失（如「距离没显示」），应调用 `display_field_missing`。

示例：
- ✅ "商户1002在列表中不展示" → 本 Skill
- ✅ "888商户没有召回" → 本 Skill
- ❌ "商户缺少距离字段" → display_field_missing

## 诊断步骤

1. 检查用户问题是否提供：商户ID和平台信息（美团/点评）；没有则询问用户。
2. 使用check_low_star_merchant检查商户是否为零星商户（shop_star=0）
3. 如果是零星商户，告知用户该商户命中零星商户卡控，建议协助商户提升星级
4. 使用check_sensitive_merchant检查商户是否为软色情违规商户（risk_score>0.5或risk_score_v2=1）
5. 如果是软色情违规商户，告知用户该商户因违规内容被过滤
6. 使用select_shop_state，查询访问商户时该商户是否正在营业

## 可用工具

- `check_low_star_merchant`
- `check_sensitive_merchant`
- `select_shop_state` ⚠️ TODO: 尚未实现

## 背景知识 / 规划提示

# 专业知识
## 常见未召回原因（优先级排序）
1. **零星商户卡控** (最常见，约40%)
   - shop_star=0 的商户会被系统过滤
   - 工具: check_low_star_merchant

2. **软色情违规** (约40%)
   - risk_score>0.5 或 risk_score_v2=1
   - 工具: check_sensitive_merchant

3. **营业状态异常** (约10%)
   - 不在营业时间
   - 工具: select_shop_state

# 输出要求
生成诊断步骤，每步明确"做什么"和"为什么"。

## 输出格式

提供结构化诊断结果，包含：
- **根因**：确认的问题根本原因
- **证据**：工具调用输出的关键数据
- **建议操作**：修复或下一步行动
