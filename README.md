# tt

## 运行入口

- FastAPI API: `uvicorn src.fastapi.app:app --host 0.0.0.0 --port 8000`
- Streamlit 调试页: `streamlit run src/ui/app.py`
- 兼容的环境变量示例见 `.env.example`

## 部署

云端部署说明见 [DEPLOY.md](DEPLOY.md)。

如果 MySQL、Redis、Qdrant 已经单独部署好了，只启动 API：

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.yml up -d --build
```

如果要在一台机器上用 Docker 同时启动 API、MySQL、Redis、Qdrant：

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.stack.yml up -d --build
```
