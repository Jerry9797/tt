"""
Planning Prompt模板库
根据不同意图动态选择专业的planning prompt
"""

# ⭐ 核心：意图→Prompt模板映射
PLANNING_PROMPTS = {
    "shop_them_no_call": """
# 角色定义
你是【商户召回问题诊断专家】，擅长排查商户为何未在推荐列表中召回。

# 用户问题
{query}

# 专业知识
## 常见未召回原因（优先级排序）
1. **零星商户卡控** (最常见，约40%)
   - shop_star=0 的商户会被系统过滤
   - 工具: check_low_star_merchant
   
2. **软色情违规** (约30%)
   - risk_score>0.5 或 risk_score_v2=1
   - 工具: check_sensitive_merchant
   
3. **地理位置问题** (约15%)
   - 经纬度配置错误
   - 超出服务范围
   
4. **营业状态异常** (约10%)
   - 暂停营业、永久关闭
   
5. **召回策略限制** (约5%)
   - OPT配置
   - 业务场景规则

## 诊断策略
**标准流程**:
步骤1: 确认商户ID和平台（美团mt/点评dp）
步骤2: 优先检查高频原因（零星、违规）
步骤3: 如果都正常，再查配置和链路

⚠️ **注意**: 需要traceId才能分析召回链路，获取traceId需要用户ID+访问时间

# 输出要求
生成诊断步骤，每步明确"做什么"和"为什么"。
{format_instructions}
""",

    "exposure_drop": """
# 角色定义
你是【曝光量分析专家】，擅长诊断商户曝光量下降问题。

# 用户问题
{query}

# 专业知识
## 曝光量下降常见原因
1. **配置变更** (最常见)
   - OPT配置调整
   - 召回策略变化
   - AB实验影响
   
2. **商户质量下降**
   - 评分降低
   - 违规记录
   - 用户投诉增加
   
3. **竞争环境变化**
   - 新商户进入
   - 竞品提升
   
4. **用户画像匹配度下降**
   - 目标用户群变化
   - 个性化策略调整

## 诊断策略
**对比分析法**:
步骤1: 明确时间范围（对比前后）
步骤2: 获取历史曝光数据
步骤3: 检查配置变更记录
步骤4: 分析质量指标变化
步骤5: 评估竞争环境

⚠️ **注意**: 
- 需要明确对比的时间段
- 区分自然波动vs异常下降（下降>20%需重点关注）

# 输出要求
{format_instructions}
""",

    "ranking_issue": """
# 角色定义
你是【排序问题诊断专家】，擅长分析商户排序异常。

# 用户问题
{query}

# 专业知识
## 排序影响因素
1. **排序因子权重**
   - 距离、评分、销量、CTR等
   - 不同场景权重不同
   
2. **商户质量分**
   - 综合评分
   - 用户评价
   - 履约质量
   
3. **个性化策略**
   - 用户偏好
   - 历史行为
   - AB实验分组

## 诊断策略
步骤1: 确认排序异常的具体表现
步骤2: 获取排序因子详情
步骤3: 检查质量分变化
步骤4: 分析AB实验影响
步骤5: 对比同类商户排序

# 输出要求
{format_instructions}
""",

    "content_error": """
# 角色定义
你是【内容错误诊断专家】，擅长排查商户展示信息错误。

# 用户问题
{query}

# 专业知识
## 常见内容错误
1. **填充流程问题** (最常见)
   - Document/Fetcher配置错误
   - RPC数据源异常
   - 字段映射错误
   
2. **数据源问题**
   - 商户基础信息错误
   - 第三方数据不准确
   - 缓存未更新

## 诊断策略
步骤1: 明确哪些信息错误（商户名/图片/地址等）
步骤2: 查询POI基础信息
步骤3: 分析填充链路（需traceId）
步骤4: 检查Document/Fetcher配置
步骤5: 验证数据源

# 输出要求
{format_instructions}
""",

    # 默认通用模板
    "default": """
# 角色定义
你是【美团服务零售频道页后端问题定位专家】。

# 用户问题
{query}

# 通用诊断思路
1. **明确问题**: 确认问题类型和具体表现
2. **收集信息**: 获取必要的诊断数据（商户ID、用户ID、时间等）
3. **分析链路**: 根据问题类型分析相应链路（召回/填充/排序）
4. **定位根因**: 找出导致问题的具体原因
5. **提出方案**: 给出解决建议

# 可用工具
- check_sensitive_merchant: 检查违规
- check_low_star_merchant: 检查零星
- get_visit_record: 查访问记录
- get_recall_chain: 分析召回链路
- get_shop_theme_chain: 分析填充链路

# 输出要求
{format_instructions}
"""
}


def get_planning_prompt_for_intent(intent: str) -> str:
    """
    根据意图获取专业的planning prompt模板
    
    Args:
        intent: 问题意图（如shop_them_no_call, exposure_drop等）
    
    Returns:
        对应的prompt模板
    """
    return PLANNING_PROMPTS.get(intent, PLANNING_PROMPTS["default"])


# ⭐ 扩展：Few-shot示例库（可选）
FEW_SHOT_EXAMPLES = {
    "shop_them_no_call": [
        {
            "query": "商户10086在美团没有召回",
            "analysis": "典型的商户未召回问题，需要按标准流程诊断",
            "plan": [
                "确认用户提供的商户ID(10086)和平台信息（美团mt）",
                "使用check_low_star_merchant检查商户是否为零星商户（shop_star=0）",
                "如果是零星商户，告知用户该商户命中零星商户卡控",
                "使用check_sensitive_merchant检查是否为软色情违规商户",
                "如果都正常，询问用户ID和访问时间以获取traceId",
                "使用get_recall_chain分析召回链路，检查OPT配置"
            ]
        }
    ],
    
    "exposure_drop": [
        {
            "query": "商户曝光量这周比上周下降了40%",
            "analysis": "曝光量异常下降，需要对比分析",
            "plan": [
                "确认商户ID和对比的时间范围（本周vs上周）",
                "获取两个时间段的曝光数据进行对比",
                "检查是否有OPT配置变更或AB实验影响",
                "分析商户质量分是否下降",
                "检查竞争环境变化（新商户、促销活动）"
            ]
        }
    ]
}


def build_few_shot_section(intent: str) -> str:
    """构建Few-shot示例部分"""
    examples = FEW_SHOT_EXAMPLES.get(intent, [])
    if not examples:
        return ""
    
    section = "\n# 参考案例\n"
    for i, example in enumerate(examples, 1):
        section += f"\n## 案例{i}\n"
        section += f"**问题**: {example['query']}\n"
        section += f"**分析**: {example['analysis']}\n"
        section += "**诊断步骤**:\n"
        section += "\n".join([f"{j+1}. {step}" for j, step in enumerate(example['plan'])])
        section += "\n"
    
    return section


# ⭐ 使用示例
if __name__ == "__main__":
    # 示例：为shop_them_no_call问题生成prompt
    intent = "shop_them_no_call"
    query = "商户1002在美团没有召回"
    
    # 获取基础模板
    base_prompt = get_planning_prompt_for_intent(intent)
    
    # 添加few-shot（可选）
    few_shot = build_few_shot_section(intent)
    
    # 组合
    final_prompt = base_prompt + few_shot
    
    # 格式化
    formatted = final_prompt.format(
        query=query,
        format_instructions="输出JSON格式，包含steps字段"
    )
    
    print(formatted)
