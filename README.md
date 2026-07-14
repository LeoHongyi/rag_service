# FBA Agentic RAG

基于 [FastAPI Best Architecture](https://docs.fba.wu-clan.cc/fastapi_best_architecture_docs/) 的 RAG 后端第一版。它提供私有/公共知识库、异步文档索引、PostgreSQL + pgvector 混合检索，以及带服务端来源引用的受限 Agentic RAG 问答。

## 已实现

- 知识库、文档、切片和查询日志的 FBA Model / CRUD / Service / API 分层。
- `.txt`、`.md`、`.docx` 上传；本地对象存储；Celery 异步解析、切分与向量化。
- pgvector 余弦候选 + PostgreSQL FTS 候选 + RRF 融合，且授权范围在 SQL 中收敛。
- OpenAI 兼容的 Chat/Embedding 适配器；未配置模型时使用确定性本地向量和安全开发回退。
- `basic`、`agentic`、`auto` 问答模式；LangGraph 明确的有界状态图和查询诊断日志。
- Alembic 初始迁移：pgvector、HNSW 向量索引和 FTS GIN 索引。

## 启动

1. 启动本地依赖：`docker compose -f docker-compose.infra.yml --env-file .env.docker.example up -d`。该 Compose 使用带 pgvector 的 PostgreSQL 16 和 Redis 7，主机端口分别为 `5432` 与 `6379`。
2. 复制 `backend/.env.example` 为 `backend/.env`，填写模型配置；本地运行时保留 `DATABASE_HOST=127.0.0.1`、`REDIS_HOST=127.0.0.1`。
3. 安装依赖：`uv sync --group dev --group lint`。
4. 执行迁移：`cd backend && uv run alembic upgrade head`。
5. 启动 FBA API 和 Celery Worker。

API 位于 `/api/v1/rag`：

- `POST /knowledge-bases`
- `POST /knowledge-bases/{id}/documents`
- `POST /retrieve`
- `POST /answer`

完整的产品范围、架构约束和交接状态见 [`AGENTS.md`](AGENTS.md)、[`docs/PRODUCT.md`](docs/PRODUCT.md)、[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) 与 [`session-handoff.md`](session-handoff.md)。
