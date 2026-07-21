# 本地调试手册

本文用于在 macOS 本地调试 FBA Agentic RAG 后端。

## 1. 前置条件

- Python 与 `uv`
- Docker Desktop
- DashScope API Key

本项目本地使用：

| 服务 | 地址 | 用途 |
| --- | --- | --- |
| PostgreSQL + pgvector | `127.0.0.1:5432` | RAG 元数据、向量、全文检索 |
| Redis | `127.0.0.1:6379` | Celery Broker |
| FastAPI | `127.0.0.1:8000` | Swagger 与 API |

## 2. 配置环境变量

复制并编辑配置：

```bash
cp backend/.env.example backend/.env
```

至少确认以下 RAG 配置：

```env
RAG_EMBEDDING_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
RAG_EMBEDDING_API_KEY='你的 DashScope Key'
RAG_EMBEDDING_MODEL='text-embedding-v4'
RAG_EMBEDDING_DIMENSIONS=1024

RAG_CHAT_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
RAG_CHAT_API_KEY='你的 DashScope Key'
RAG_CHAT_MODEL='qwen-plus'
```

`RAG_EMBEDDING_DIMENSIONS` 必须是 `1024`，因为数据库切片列是 `vector(1024)`。

## 3. 启动基础设施

如果本机具备 Docker Compose：

```bash
docker compose -f docker-compose.infra.yml --env-file .env.docker.example up -d
```

如果 Docker CLI 没有 Compose 插件，可使用：

```bash
docker start rag_postgres rag_redis
```

验证：

```bash
docker exec rag_postgres pg_isready -U postgres -d fba
docker exec rag_postgres psql -U postgres -d fba -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
docker exec rag_redis redis-cli ping
```

预期为 PostgreSQL “accepting connections”、pgvector 版本号和 `PONG`。

## 4. 安装依赖与迁移

在项目根目录执行：

```bash
uv sync --group dev --group lint
cd backend
uv run alembic upgrade head
cd ..
```

## 5. 启动 API、Worker 与 Beat

分别开两个终端，都位于项目根目录：

```bash
uv run fba run --host 127.0.0.1 --port 8000 --no-reload
```

```bash
uv run fba celery worker --log-level info
```

P0 使用事务 Outbox 投递文档索引任务，因此还必须启动 Beat；它每 5 秒将已提交事件发送给 Worker：

```bash
uv run fba celery beat --log-level info
```

注意：`fba run` 必须在项目根目录运行；在 `backend/` 目录运行会造成模块路径解析错误。

## 6. Swagger 手工测试

打开：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

1. 调用 `POST /api/v1/auth/login/swagger`，输入 `username` 和 `password`。
2. 从响应复制 `access_token`。
3. 点击右上角 **Authorize**，粘贴 `Bearer <access_token>`。
4. 创建知识库：`POST /api/v1/rag/knowledge-bases`。
5. 上传测试文档：`POST /api/v1/rag/knowledge-bases/{knowledge_base_id}/documents`。
6. 查询 `GET /api/v1/rag/knowledge-bases/{knowledge_base_id}/documents/{pk}`，等待状态变成 `READY`。
7. 调用 `POST /api/v1/rag/retrieve` 或 `POST /api/v1/rag/answer`。

可上传的样例文件：

```text
backend/tests/fixtures/rag_retrieval_demo.md
```

推荐问题：`P0 事故多久内建立事故频道？`

## 7. cURL 快速检查

```bash
curl http://127.0.0.1:8000/openapi
curl http://127.0.0.1:8000/docs
```

API 正常时应返回 `200`。

## 8. 自动化核心测试

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
uv run pytest --confcutdir=backend/tests/rag \
  backend/tests/rag/test_chunking.py backend/tests/rag/test_agent.py -q
```

完整 FBA 测试会加载 `backend/conftest.py` 并要求 Redis 与 PostgreSQL 正常运行。

## 9. 常见问题

### 文档一直是 `PENDING`

确认 Celery Worker 与 Beat 都正在运行。先观察 Beat 日志中的 `rag_dispatch_outbox`，再观察 Worker 日志中的 `rag_index_document`。同时检查 Redis：

```bash
docker exec rag_redis redis-cli -n 1 LLEN celery
```

### 文档变为 `FAILED`

通过文档详情接口查看 `error_message`。常见原因是文件类型不受支持、DashScope Key 无效、网络不可达，或 Embedding 向量维度与 `1024` 不一致。

### 问答返回“未配置聊天模型”

检查 `backend/.env` 的 `RAG_CHAT_BASE_URL`、`RAG_CHAT_API_KEY` 和 `RAG_CHAT_MODEL`。修改后必须重启 API；修改 Embedding 配置后还应重启 Worker 并重试索引。

### 端口已被占用

检查进程：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5432 -sTCP:LISTEN
lsof -nP -iTCP:6379 -sTCP:LISTEN
```

### 为什么更新 Embedding 模型后需要重新索引？

文档和查询必须位于同一向量空间。更新模型或向量维度后，旧切片向量无法与新查询向量可靠比较，因此必须重新索引。
