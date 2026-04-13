# tt v2 — Claude Agent SDK

美团后端诊断助手 v2。基于 Claude Code SDK，不再挂载 MCP 自定义工具。

## 结构

```
v2/
├── skills/
│   └── shop_them_no_call/  ← 商户未召回 SOP
│       └── SKILL.md
├── agent.py          ← 主入口：query() 直接运行
├── telemetry.py      ← OpenTelemetry 初始化
├── docker-compose.telemetry.yml ← 本地监控栈
├── TELEMETRY.md      ← 监控说明
└── requirements.txt  ← 依赖
```

## 使用

```bash
# 单次查询
.venv/bin/python v2/agent.py "商户1002在美团列表中不展示"
```

## 工具说明

当前版本保留 Claude Code SDK，但不再注册 `src/tools/` 中的 MCP 自定义工具。
`skills/` 仍用于提供 SOP 文本说明；如果诊断依赖外部工具数据，助手会直接说明缺失信息。

## 范围限定（v1）

- 单轮对话（无会话持久化）
- 无 HIL（Human-in-the-loop）
- 无 FastAPI 包装层
- 无 MCP 自定义工具
