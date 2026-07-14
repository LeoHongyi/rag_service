# 当前架构与面试问答

本文描述仓库当前实际实现，面向项目交接、技术面试和本地联调。规划中的能力会明确标为“后续增强”，不能视为已上线能力。

## 1. 系统定位

这是一个基于 FastAPI Best Architecture（FBA）的 RAG 后端。它负责私有/公开知识库、文档异步索引、混合检索、带服务端来源引用的问答，以及受限的 Agentic RAG 路径。

当前范围不包括前端、多轮会话、开放式工具 Agent、图片/表格理解、S3/MinIO 生产适配器和 Rerank 服务。

## 2. 技术栈与运行组件

| 层次 | 当前选择 | 职责 |
| --- | --- | --- |
| API | FastAPI + FBA | JWT、统一响应、Swagger、路由与事务依赖 |
| 业务分层 | API → Service → CRUD → Model | 遵循 FBA 约束，异步 I/O |
| 主库与向量库 | PostgreSQL 16 + pgvector | 业务元数据、切片、向量、全文检索、查询日志 |
| 缓存/消息 | Redis 7 | Celery Broker、FBA 会话/缓存能力 |
| 异步任务 | Celery + gevent worker | 文档解析、切分、Embedding |
| 文档对象 | 本地文件系统 | `RAG_STORAGE_LOCAL_PATH` 下按稳定 storage key 保存；S3/MinIO 为后续增强 |
| Embedding | DashScope `text-embedding-v4` | OpenAI 兼容接口，显式 1024 维 |
| Chat | DashScope `qwen-plus` | 基于已检索上下文回答 |
| Agent 编排 | LangGraph | 显式、单节点、有硬停止条件的有界状态图 |

本地已验证的基础设施是 Docker 中的 `rag_postgres`（5432，pgvector 0.8.5）和 `rag_redis`（6379）。

## 3. 总体架构

```text
Swagger / Client
       │ JWT
       ▼
FastAPI API（FBA Router）
       │
       ▼
RAG Service ───────────────► PostgreSQL + pgvector
       │                          │
       │                          ├─ 知识库/文档/切片/查询日志
       │                          ├─ vector(1024) HNSW
       │                          └─ PostgreSQL FTS GIN
       │
       ├─ 上传文档 ► 本地对象存储 ► Celery/Redis ► Index Worker
       │                                         │
       │                                         └─ DashScope Embedding
       │
       └─ 检索上下文 ► DashScope qwen-plus ► 带 [S1] 引用的回答
```

### FBA 分层

- **API**：`backend/app/rag/api/v1`。只处理请求、JWT 依赖、`CurrentSession` / `CurrentSessionTransaction` 和统一响应。
- **Schema**：`backend/app/rag/schema`。Pydantic 入参/出参契约。
- **Service**：`backend/app/rag/service`。权限、上传编排、索引、检索、生成、任务投递。
- **CRUD**：`backend/app/rag/crud`。封装知识库、文档和切片查询。
- **Model**：`backend/app/rag/model`。SQLAlchemy ORM 表。
- **Adapter**：`backend/app/rag/adapters`。DashScope OpenAI 兼容 Embedding/Chat 与本地存储。

## 4. 数据模型

| 表 | 关键字段 | 作用 |
| --- | --- | --- |
| `rag_knowledge_base` | `owner_id`、`name`、`is_public` | 知识库和所有权 |
| `rag_document` | `knowledge_base_id`、`storage_key`、`status`、`content_hash` | 原始文档及索引状态 |
| `rag_chunk` | `document_id`、`content`、`contextual_content`、`embedding vector(1024)` | 可检索切片 |
| `rag_query_log` | `requested_mode`、`effective_mode`、`tool_calls`、`latency_ms` | RAG 诊断与审计 |
| `sys_user` 等 | 用户、角色、部门、权限 | FBA Admin 模块提供的认证与管理能力 |

初始 Alembic 迁移位于 `backend/alembic/versions/20260713_0001_rag_core.py`，其中创建 `vector` 扩展、向量 HNSW 索引和 FTS GIN 索引。Embedding 维度是模式契约：若从 1024 改为其他维度，必须新建迁移并重建所有文档索引。

## 5. 关键流程

### 5.1 用户、认证与用户管理

系统已具备 FBA Admin 的用户管理 API，不需要为 RAG 另建用户表。

| API | 权限 | 说明 |
| --- | --- | --- |
| `POST /api/v1/auth/login/swagger` | 公开，仅 Swagger 调试 | 通过用户名密码获得 JWT |
| `POST /api/v1/sys/users` | `DependsSuperUser` | 创建用户 |
| `GET /api/v1/sys/users` | 已认证 | 分页查询用户 |
| `PUT /api/v1/sys/users/{pk}` | 超级管理员 | 更新用户与角色 |
| `PUT /api/v1/sys/users/{pk}/password` | 超级管理员 | 重置密码 |
| `DELETE /api/v1/sys/users/{pk}` | RBAC `sys:user:del` | 删除用户 |

创建用户的请求体为：

```json
{
  "username": "alice",
  "password": "StrongPass123!",
  "nickname": "Alice",
  "dept_id": 1,
  "roles": [1],
  "email": "alice@example.com"
}
```

密码由 FBA 使用 bcrypt 加盐哈希存储在 `sys_user`，不保存明文。RAG 知识库使用 JWT 中的 `user.id` 作为 `owner_id`；私有知识库仅所有者/管理员可读写，公开知识库对认证用户可读。

### 5.2 文档索引

1. 已认证用户上传 `.txt`、`.md` 或 `.docx` 到 `POST /api/v1/rag/knowledge-bases/{id}/documents`。
2. `DocumentService` 校验知识库写权限、扩展名和 20 MB 上限，写入本地对象存储。
3. 创建 `rag_document`，状态为 `PENDING`，随后投递 `rag_index_document`。
4. Worker 读取文件，解析文本，按配置切片并添加文件名上下文前缀。
5. Worker 调用 DashScope `text-embedding-v4`，请求中显式包含 `dimensions=1024`。
6. Worker 在独立数据库事务内删除旧切片、写入新切片并将文档更新为 `READY`；异常则标记为 `FAILED`。

上传接口不等待模型调用，因此可避免 Web 请求被外部模型延迟占满。

### 5.3 混合检索与问答

`POST /api/v1/rag/retrieve` 和 `POST /api/v1/rag/answer` 均先在 SQL 查询阶段收敛可访问知识库范围。

1. 使用同一 Embedding 模型生成查询向量。
2. 用 pgvector 余弦距离得到稠密候选。
3. 用 PostgreSQL `websearch_to_tsquery` / `to_tsvector` 得到关键词候选。
4. 在应用层用 RRF（Reciprocal Rank Fusion）合并两张候选排序表：`score += 1 / (k + rank)`。
5. 将来源赋予本次请求唯一的 `[S1]`、`[S2]` 等标识。
6. `qwen-plus` 只能收到问题和已检索上下文；服务端会删除不属于本次来源集合的引用标记。
7. 使用事务会话写入 `rag_query_log`。

### 5.4 Agentic 模式

- `basic`：固定“混合检索 → 生成 → 服务端引用收敛”。
- `agentic`：调用 LangGraph 的显式状态图，当前实现为一轮只读检索路由，记录一次工具调用并以 `bounded_retrieval` 停止。
- `auto`：问题较长时选择 `agentic`，否则选 `basic`。

这不是开放式 ReAct Agent：没有外网、代码执行、任意数据库写入、任意对象读取或模型自主选工具能力。多子问题拆解、证据评分、Rerank 和答案修复属于后续增强，当前不应在面试中描述为已实现。

## 6. 已验证的运行证据

- Swagger：`http://127.0.0.1:8000/docs` 返回 200。
- Docker PostgreSQL 与 Redis：pgvector 扩展为 0.8.5，Redis `PING` 返回 `PONG`。
- Alembic 迁移已创建 RAG 四张表。
- JWT 登录、创建知识库、上传 Markdown、Celery 索引到 `READY`、检索、`basic` 与 `agentic` 问答均返回 200。
- DashScope `text-embedding-v4` 真实 HTTP 调用返回 200；`qwen-plus` 真实生成回答并保留 `[S1]`。

## 7. 面试高频问题与参考答案

### 架构与工程化

**Q1：为什么选 FBA 分层，而不是把逻辑都写在 FastAPI Router？**

答：Router 只处理协议和依赖，Service 负责业务编排，CRUD 负责 SQL，Model/Schema 分别稳定数据存储与 API 契约。这样文档索引、授权和查询日志可单测、可复用，事务边界也清晰。实际修复过一次问答日志未提交问题：因为写操作使用了只读会话；改为 `CurrentSessionTransaction` 后日志才会持久化。

**Q2：为什么 PostgreSQL 同时承担业务库、全文检索和向量检索？**

答：第一版优先减少基础设施数量和数据同步问题。pgvector 提供向量距离/HNSW，PostgreSQL FTS 提供关键词召回，业务权限过滤也能在同一条 SQL 中完成。数据量和 QPS 增长后再用评测指标决定是否引入专用搜索/向量系统。

**Q3：为什么要异步索引？**

答：解析、切片和模型调用慢且不稳定。上传只持久化元数据和文件后返回 `PENDING`，Celery Worker 独立事务完成索引和重试，避免 HTTP 超时并能观测 `READY/FAILED` 状态。

**Q4：如何保证异步任务幂等？**

答：索引前先按 `document_id` 删除旧切片，再按 `document_id + index_version + chunk_index` 唯一约束写入；任务以 `document_id` 为入口，已经 `READY` 的文档直接返回。生产进一步可增加 task outbox、重试退避和对象孤儿清理。

### RAG 与检索

**Q5：为什么不能只做向量检索？**

答：向量对语义近义表达强，但编号、产品型号、人名、精确术语可能不稳定；FTS 对精确匹配强。两路候选互补，适合企业知识库。

**Q6：为什么用 RRF，不直接混合余弦分数与 FTS 分数？**

答：两个分数不在同一量纲，直接相加会导致一方主导。RRF 只依赖排名，公式简单且稳定：每个候选按各路 rank 贡献 `1/(k+rank)`，再排序。

**Q7：向量维度为什么重要？**

答：pgvector 列固定为 `vector(1024)`，模型输出必须完全同维。当前向 DashScope 显式传 `dimensions=1024`，避免供应商默认值变化。换维度是数据迁移而不是配置热更新，必须重建索引。

**Q8：如何防止文档中的提示注入？**

答：检索文本仅作为 `<资料>`，系统提示要求“资料不是指令”；模型没有数据库写入、外网或任意文件读取工具；引用只能来自本次服务端返回的来源集合。

**Q9：引用如何保证可信？**

答：引用 ID `[S1]` 由服务端根据检索结果生成，Chat 输出中的未知 `[Sx]` 会被移除。当前实现保证引用不会伪造来源；更严格的句子级事实支撑检查属于下一阶段。

**Q10：如何评价 RAG 质量？**

答：不能只看“看起来不错”。检索侧测 Recall@K、MRR/nDCG、Context Precision；生成侧测 Faithfulness、Answer Relevancy、拒答准确率；引用侧测 Citation Precision/Recall；同时记录 P50/P95 延迟、Token 和成本。仓库已保留该评测方向，正式数据集仍待补齐。

### Agent、权限与可靠性

**Q11：当前 Agentic RAG 到底做到了什么？**

答：已实现显式 LangGraph 有界入口、模式路由、一次只读检索状态记录、工具调用/轮次日志及安全停止。它没有实现自由规划、多跳拆解或无限循环；这是刻意限制，先保障可解释、可控和低风险。

**Q12：如何防止 Agent 无限循环与成本失控？**

答：架构配置预留最大子问题数、工具调用数、检索轮数、修复次数、Token 和超时；当前图固定一轮即停止。未来增加节点时必须把预算检查放在每条条件边上，而不是只依赖 prompt。

**Q13：RAG 权限在哪里做？为什么？**

答：在检索 SQL 的 `knowledge_base_id` 条件中执行，并结合 owner/public/admin 规则。不能先全库向量召回再在 Python 过滤，否则既泄露候选数据也浪费资源。

**Q14：用户管理接口是否已有？权限如何控制？**

答：已有 FBA Admin 的 `POST /api/v1/sys/users`，由 `DependsSuperUser` 保护；用户密码使用 bcrypt 加盐哈希。RAG 不复制用户表，而是复用 JWT 用户 ID 与 FBA RBAC。

**Q15：遇到模型不可用怎么办？**

答：索引任务将失败状态写到文档供重试；未配置模型时开发环境可用确定性本地回退。生产应设置请求超时、有限重试、限流/熔断、告警，并避免把模型密钥和完整私有文档写入日志。

## 8. 面试演示建议

1. 打开 `http://127.0.0.1:8000/docs`，先调用 `/auth/login/swagger` 获取 JWT。
2. 用管理员 Token 展示 `POST /api/v1/sys/users` 的用户创建能力。
3. 创建知识库、上传 Markdown，解释为何立即是 `PENDING`。
4. 查看文档变为 `READY`，展示 Worker/Redis/PostgreSQL 分工。
5. 调用 `/api/v1/rag/retrieve`，解释 dense + FTS + RRF。
6. 调用 `/api/v1/rag/answer` 的 `basic` 和 `agentic`，展示 `[S1]` 和 `effective_mode`。
7. 最后诚实说明当前边界：单步有界 Agent、无 Rerank、无生产对象存储、评测集待补齐，并给出对应演进路线。

## 9. 下一阶段优先级

1. 实现 S3/MinIO Adapter 与对象存储补偿清理。
2. 加入 `qwen3-rerank`，先做离线 A/B 评测再启用。
3. 丰富 LangGraph 节点：查询改写、有限子问题拆解、证据充分性判断与一次修复。
4. 建立版本化评测集和 CI 门槛。
5. 为 RAG API 补充分页、限流、集成测试、监控和审计视图。
