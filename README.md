# tt

## 运行入口

- FastAPI API: `uvicorn src.fastapi.app:app --host 0.0.0.0 --port 8000`
- Streamlit 调试页: `streamlit run src/ui/app.py`

## 部署

云端部署说明见 [DEPLOY.md](DEPLOY.md)。

如果要在一台机器上用 Docker 同时启动 API、MySQL、Redis、Qdrant，可直接执行：

```bash
cp .env1.example .env1
docker compose -f deploy/docker-compose.stack.yml up -d --build
```
