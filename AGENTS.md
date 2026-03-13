# Repository Guidelines

## 项目结构与模块组织
核心代码位于 `src/`。其中 `src/nodes/` 存放 LangGraph 工作流节点，`src/tools/` 存放工具集成，`src/config/` 存放服务与模型配置，`src/utils/` 存放通用基础设施辅助代码。API 入口在 `src/fastapi/app.py`，Streamlit 调试界面在 `src/ui/app.py`。提示词与 SOP 数据位于 `src/prompt/` 和 `src/config/`。实验性代码请放在 `src/demo/` 或 `脚本/`，不要混入生产模块。新增生产代码时，测试目录建议在 `tests/` 中按相同结构映射。

## 构建、测试与开发命令
当前仓库以源码运行为主，尚未提交统一的构建系统。

- `source .venv/bin/activate`：激活本地 Python 虚拟环境。
- `python src/fastapi/app.py`：启动 FastAPI 服务，默认监听 `8000` 端口。
- `streamlit run src/ui/app.py`：启动本地调试 UI。
- `python main.py`：运行提示词/Token 统计相关的冒烟脚本。
- `python -m pytest tests`：运行测试；行为变更在合并前应补齐测试。

## 编码风格与命名约定
遵循标准 Python 风格：4 空格缩进，模块、函数、变量使用 `snake_case`，类和 Pydantic 模型使用 `PascalCase`，例如 `ChatRequest`。导入顺序保持为标准库、第三方库、本地包。优先编写职责单一、粒度清晰的节点与工具模块。仓库目前没有已提交的格式化或静态检查配置，因此请保持 PEP 8 一致性，并避免将大规模重构与功能修改混在同一次提交中。

## 测试指南
当前已提交的 `tests/` 目录为空，因此新增功能时应同步补充覆盖。测试文件命名使用 `test_<module>.py`，并尽量映射 `src/` 目录结构。优先为 `src/fastapi/app.py`、`src/nodes/build_graph.py` 以及依赖 LLM、MySQL、Redis 的工具模块编写冒烟测试和隔离测试。若改动涉及外部服务，请在 PR 中至少附上一条手动验证命令。

## 提交与 Pull Request 规范
最近的提交历史多为 `add`、`add code` 这类简短信息；后续提交应更明确且范围清晰，例如 `feat(nodes): add SOP fallback` 或 `fix(config): handle missing Redis password`。Pull Request 应说明用户可见的行为变化，列出新增或变更的环境变量与配置项，写明本地执行过的命令；如果修改了 `src/ui/`，请附截图；如果修改了 API，请附示例请求/响应。

## 安全与配置提示
敏感信息必须保存在 `.env`，不要提交 API Key、数据库凭据或生产数据副本。新增环境变量时，请在 PR 描述中说明用途，并确保默认值适合本地开发环境。
