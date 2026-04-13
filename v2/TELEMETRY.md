# v2 Telemetry

## 启动观测栈

```bash
cd v2
./run_telemetry_stack.sh
```

启动后访问：

- Grafana: `http://127.0.0.1:3000`

## 运行 Agent 并上报 telemetry

```bash
cd v2
./run_with_telemetry.sh "商户1002在美团列表中不展示"
```

默认配置：

- OTLP endpoint: `http://127.0.0.1:4318`
- OTLP protocol: `http/protobuf`
- service name: `tt-v2-agent`
- traces / metrics / logs 全部开启

## 常用检查

查看容器状态：

```bash
docker compose -f docker-compose.telemetry.yml ps
```

查看容器日志：

```bash
docker compose -f docker-compose.telemetry.yml logs -f
```

停止观测栈：

```bash
docker compose -f docker-compose.telemetry.yml down
```
