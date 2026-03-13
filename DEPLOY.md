# 云端部署

当前仓库的推荐部署方式是：

- 仅发布 FastAPI API。
- 应用运行在单台 Linux 云主机的 Docker 容器中。
- MySQL、Redis 使用托管实例。
- Nginx 负责 HTTPS 和反向代理。

如果你准备把 API、MySQL、Redis、Qdrant 一起部署到同一台机器的 Docker 中，也可以直接使用 [`deploy/docker-compose.stack.yml`](deploy/docker-compose.stack.yml)。

## 1. 部署前准备

在云平台准备以下资源：

- 1 台 Linux 云主机，开放 `80/443`。
- 1 个 MySQL 实例，并把云主机出口 IP 加入白名单。
- 1 个 Redis 实例，并把云主机出口 IP 加入白名单。
- 1 个可用的 Qdrant 服务地址；如果不启用 FAQ 检索，也建议配置连通性，避免线上行为和本地偏差过大。

将本地 `.env` 按照 [`.env.example`](.env.example) 的键名整理为生产环境变量，不要上传真实密钥到代码仓库。

## 2. 安装运行时

在云主机安装：

- Docker Engine
- Docker Compose Plugin
- Nginx

## 3. 发布应用

将仓库拉到服务器后，在项目根目录执行：

```bash
cp .env1.example .env1
vim .env1
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

如果你要在同一台机器上把 API、MySQL、Redis、Qdrant 一起拉起：

```bash
cp .env1.example .env1
vim .env1
docker compose -f deploy/docker-compose.stack.yml up -d --build
```

这种模式下，`.env` 里应该保留容器服务名：

```dotenv
MYSQL_HOST=mysql
REDIS_HOST=redis
QDRANT_HOST=qdrant
```

不要改成 `127.0.0.1`。因为 API 运行在容器内时，`127.0.0.1` 指向的是 API 容器自己，不是 MySQL、Redis 或 Qdrant 容器。

确认应用启动成功：

```bash
curl http://127.0.0.1:8000/health
```

预期返回：

```json
{"status":"healthy"}
```

## 4. 配置 Nginx

将 [`deploy/nginx.conf`](deploy/nginx.conf) 放到站点配置中，并将 `server_name` 改成你的域名。

关键点：

- `/chat/stream` 必须关闭 `proxy_buffering`，否则 SSE 会被缓存。
- `proxy_read_timeout` 和 `proxy_send_timeout` 需要足够大，避免长任务被代理断开。
- 建议用 Certbot 或云厂商证书服务补齐 HTTPS。

## 5. 验证 API

健康检查：

```bash
curl https://your-domain.example/health
```

普通对话：

```bash
curl -X POST https://your-domain.example/chat \
  -H 'Content-Type: application/json' \
  -d '{"query":"你好","thread_id":"deploy-smoke"}'
```

流式对话：

```bash
curl -N -X POST https://your-domain.example/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"query":"你好","thread_id":"deploy-stream"}'
```

## 6. 运维建议

- 只对公网暴露 `80/443`，不要直接暴露 `8000`。
- 容器日志通过 `docker compose logs -f api` 查看。
- 先用 `/health` 做存活检查；如果后续需要更强校验，再增加数据库和 Redis 连通性检查。
- 如果要迁移 Qdrant，请只修改环境变量 `QDRANT_HOST`、`QDRANT_PORT`、`QDRANT_API_KEY`、`QDRANT_HTTPS`，不要改代码。
- 如果 API 和中间件都在 Compose 里，优先使用服务名互联，不要使用 `127.0.0.1`。
