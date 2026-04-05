# tt

## 运行入口

- FastAPI API: `uvicorn src.fastapi.app:app --host 0.0.0.0 --port 8000`
- Streamlit 调试页: `streamlit run src/ui/app.py`
- 兼容的环境变量示例见 `.env.example`

## LangSmith

本项目采用 LangSmith 官方环境变量做最小接入。安装依赖并在 `.env` 中配置后，LangChain/LangGraph 调用会自动上报 tracing，不需要额外改业务代码。

```dotenv
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=tt
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

说明：

- 未配置 `LANGSMITH_API_KEY` 时，应用仍可正常运行，只是不产生 LangSmith trace。
- FastAPI 与 Streamlit 共用同一套环境变量，两个入口都会按当前进程环境决定是否上报。

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
