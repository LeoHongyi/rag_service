# session-handoff.md

## 当前目标

基于 FastAPI Best Architecture（FBA）从零建设一套 RAG 与 Agentic RAG 知识库后端。当前只实现知识索引、混合检索、有界 Agentic 编排和带引用问答，不包含通用聊天、开放式 Agent、支付、图片生成、客服工单或前端。

## 最新实施状态（2026-07-13）

第一版核心代码已完成，旧的阶段清单保留为后续增强项，不再表示当前仓库为空。

- 已以官方 FBA 模板初始化工程，并注册 `backend/app/rag` 路由。
- 已实现知识库、文档、切片、查询日志的 Model / CRUD / Service / Schema / API；API 前缀为 `/api/v1/rag`。
- 已实现本地对象存储、TXT/Markdown/DOCX 解析、配置化切分、确定性上下文化、OpenAI 兼容 Embedding/Chat 适配器与无密钥开发回退。
- 文档上传快速返回 `PENDING`，Celery `rag_index_document` 负责解析、切片和嵌入；支持状态读取、切片查看、重试和删除。
- 已实现授权范围内的 pgvector 余弦检索、PostgreSQL 全文检索和 RRF 融合；问答记录 trace、轮数、工具调用数和延迟。
- 已实现明确终止的 LangGraph 状态图；它不暴露外网、代码执行或写入工具。
- 已添加 `20260713_0001_rag_core` Alembic 初始迁移，创建 pgvector/FTS/HNSW 索引。
- 已更新 Docker Compose，使 API 与 Celery Worker 共享本地 RAG 对象卷。
- 已新增独立 `docker-compose.infra.yml`，用于本地启动 pgvector PostgreSQL 16 与 Redis 7，不依赖缺失的完整 FBA 部署目录。
- 本地 Docker 已启动 `rag_postgres`（5432，pgvector 0.8.5）与 `rag_redis`（6379）；迁移命令依赖已补全的 `backend/alembic.ini` 配置。

### 本轮验证

- `python -m compileall -q backend/app/rag backend/app/task/tasks/rag backend/alembic/versions` 通过。
- `pytest --confcutdir=backend/tests/rag backend/tests/rag/test_chunking.py backend/tests/rag/test_agent.py -q`：4 passed。
- 已验证 RAG 服务和 Celery 任务模块可导入。
- 已完成本地端到端验证：JWT 登录、创建知识库、上传 Markdown、Celery 索引至 READY、混合检索、basic/agentic 问答均返回 200；修复了 Worker 文档读取与问答日志事务问题。
- 已配置并验证 DashScope OpenAI 兼容模型：`text-embedding-v4`（显式 1024 维）和 `qwen-plus`。Worker 的真实 Embedding HTTP 调用返回 200，重建后的 Agentic 问答返回模型生成答案与服务端来源引用。
- 已补充 `docs/CURRENT_ARCHITECTURE_AND_INTERVIEW.md`，覆盖实际架构、用户管理接口、已验证链路、项目边界与面试问答。
- 已补充 `docs/LOCAL_DEBUGGING.md`，用于本地 Docker、API/Worker、Swagger、RAG 索引与故障排查。
- 未执行完整 FBA 集成测试：其根 `backend/conftest.py` 在收集时会启动 FBA App 并连接 Redis；当前沙箱没有可访问的 Redis/PostgreSQL/Docker Compose。

### 下一位开发者优先验证

1. 启动 PostgreSQL（带 pgvector）、Redis 和 Celery 后执行 `cd backend && uv run alembic upgrade head`。
2. 用真实 JWT 走“创建知识库 → 上传文档 → 等待 READY → retrieve → answer”链路。
3. 配置生产 Embedding/Chat 模型并确认向量维度与迁移 `vector(1024)` 一致。
4. 再实现 S3/MinIO 适配器、重排器、真正的多步 Agent 节点和离线评测；这些属于第一版后的质量增强，不能在未评测前默认启用。

## 已完成

- [x] 读取参考 Harness：`/Users/leo/Downloads/app/AGENTS.md`。
- [x] 读取参考产品文档：`/Users/leo/Downloads/app/docs/PRODUCT.md`。
- [x] 读取参考架构文档：`/Users/leo/Downloads/app/docs/ARCHITECTURE.md`。
- [x] 读取参考交接文档：`/Users/leo/Downloads/app/session-handoff.md`。
- [x] 盘点原 RAG 项目的知识库、文档和检索问答能力。
- [x] 确定使用 FBA 的 API / Service / CRUD / Model 分层。
- [x] 确定 PostgreSQL + pgvector、Redis、Celery 和 S3 兼容对象存储。
- [x] 确定 RAG 是 `backend/app/rag` 核心模块，不作为插件。
- [x] 创建本项目 `AGENTS.md`。
- [x] 创建 `docs/PRODUCT.md`。
- [x] 创建 `docs/ARCHITECTURE.md`。
- [x] 创建 `session-handoff.md`。
- [x] 调研 LangGraph Agentic RAG、Hybrid RAG、Contextual Retrieval、pgvector 混合检索、GraphRAG、RAG/Agent 评测和 OWASP Agentic 风险的一手资料。
- [x] 将检索升级为稠密 + PostgreSQL 全文检索 + RRF + 可选 Reranker。
- [x] 确定上下文化父子切片、严格来源校验和文档提示注入隔离策略。
- [x] 确定 `basic`、`agentic`、`auto` 三种问答模式及有界 LangGraph 状态图。
- [x] 确定 Agent 子问题、工具调用、检索轮次、修复次数、Token、成本和超时硬预算。
- [x] 增加检索、生成、引用、路由、工具调用、质量、延迟和成本评测要求。

## 未完成 / 待处理

### 阶段一：项目基础

- [ ] 使用官方 FBA 当前稳定版本初始化项目。
- [ ] 固定 Python 和依赖版本，补充锁文件。
- [ ] 配置 PostgreSQL、pgvector、Redis、Celery 和 MinIO。
- [ ] 创建 `.env.example`，确认真实密钥被 Git 忽略。
- [ ] 注册 `backend/app/rag` 路由和模型。
- [ ] 增加 API、Worker 和依赖服务的健康检查。

### 阶段二：数据模型和权限

- [ ] 创建知识库 Model、Schema、CRUD、Service 和 API。
- [ ] 创建文档 Model、Schema、CRUD、Service 和 API。
- [ ] 创建切片与查询日志 Model。
- [ ] 为切片增加父级关系、上下文化内容、分词文本、`tsvector` 和结构定位元数据。
- [ ] 创建 pgvector 扩展、全文检索 GIN 索引和初始 Alembic 迁移。
- [ ] 实现所有者、管理员和公共知识库读取权限。
- [ ] 补充越权访问测试。

### 阶段三：文档索引

- [ ] 实现 S3/MinIO Storage Adapter。
- [ ] 实现 TXT、Markdown 和 DOCX Parser。
- [ ] 实现清洗、切分、重叠和 Token 统计。
- [ ] 实现标题路径、父子切片、相邻窗口和确定性上下文前缀。
- [ ] 实现固定版本中文分词与索引/查询一致性测试。
- [ ] 实现 Embedding Provider 适配器。
- [ ] 实现 Celery 索引任务、状态机、幂等和有限重试。
- [ ] 实现状态查询、预览、切片列表、重试和删除清理。
- [ ] 补充解析、切分、失败和重试测试。

### 阶段四：检索与问答

- [ ] 实现授权范围内的 pgvector 余弦检索和 PostgreSQL 全文检索。
- [ ] 实现 RRF 融合、最低相关度、单文档上限和来源去重。
- [ ] 实现可插拔 Rerank Provider 及超时降级。
- [ ] 实现父级/相邻上下文扩展和上下文 Token 预算。
- [ ] 实现 `/api/v1/rag/retrieve`。
- [ ] 实现 Chat Provider 适配器与上下文构建。
- [ ] 实现 `basic` 模式 `/api/v1/rag/answer` 和服务端结构化来源校验。
- [ ] 实现 LangGraph Typed State、路由、改写/拆解、并行检索和证据分级。
- [ ] 实现答案事实/引用校验、一次修复、预算停止和安全降级。
- [ ] 实现 `agentic` 与 `auto` 模式。
- [ ] 补充上下文不足、模型失败、权限、提示注入和超预算测试。

### 阶段五：评测

- [ ] 创建版本化领域评测集和基础 RAG 基线。
- [ ] 实现 Recall@K、MRR/nDCG、Context Precision/Recall。
- [ ] 实现 Faithfulness、Answer Relevancy、正确性和拒答准确率。
- [ ] 实现 Citation Precision/Recall 与无效引用率。
- [ ] 实现 Route Accuracy、Tool Call Accuracy、Goal Accuracy 与循环/预算指标。
- [ ] 对比 `basic` 与 `agentic` 的 P50/P95 延迟、Token、模型调用数和估算成本。
- [ ] 人工复核关键版本样本，确定 Agentic 默认启用门槛。

### 阶段六：验收与交付

- [ ] Ruff、类型检查和全部测试通过。
- [ ] 验证 Alembic 空库升级和降级。
- [ ] 验证完整 RAG 链路。
- [ ] 验证简单问题走基础路径、复杂问题有界升级、证据不足安全停止。
- [ ] 验证检索文档中的提示注入无法触发越权或非只读工具。
- [ ] 验证 Docker Compose 环境。
- [ ] 编写项目 README 和 API 使用示例。
- [ ] 更新全部 Harness 文档和本交接文件。

## 未验证

- [ ] FBA 官方模板是否能在当前机器直接启动。
- [ ] PostgreSQL 是否已安装 pgvector 扩展。
- [ ] Redis、Celery 和 MinIO 本地环境是否可用。
- [ ] 目标模型网关的聊天与 Embedding 模型 ID、维度和配额。
- [ ] DOCX 样例在限制条件下的解析效果。
- [ ] 20 MB 文件上限是否满足最终部署网关限制。
- [ ] 目标 Chat 模型是否稳定支持工具调用和严格结构化输出。
- [ ] PostgreSQL 中文分词方案在真实语料上的精确术语召回。
- [ ] Rerank 服务的质量收益、P95 延迟、价格和数据合规要求。
- [ ] 默认 Agentic 预算能否在 30 秒内覆盖目标复杂问题。
- [ ] 领域评测集的样本量、人工标注标准和上线阈值。

## 已确定的架构决策

- RAG 为核心应用模块，目录为 `backend/app/rag`。
- 第一版使用 PostgreSQL + pgvector，不引入独立向量数据库。
- 文档索引使用 Celery 异步任务，Redis 作为 Broker。
- 原始文件存储使用 S3 兼容接口，本地开发默认 MinIO。
- 模型调用通过 OpenAI 兼容适配器，供应商和模型可配置。
- 第一版问答使用普通 JSON 响应，不承诺 SSE。
- 第一版只支持 `.txt`、`.md`、`.docx`，单文件默认不超过 20 MB。
- 第一版不实现通用多轮聊天、前端、支付、图片和工单功能。
- 默认查询模式为 `auto`：简单问题走 `basic`，复杂或证据不足时进入有界 `agentic`。
- Agentic 编排使用显式 LangGraph 状态图，不使用无限制 ReAct 循环。
- 检索使用 pgvector + PostgreSQL 全文检索 + RRF，可选 Reranker 失败时降级。
- Agent 工具只读且由服务端注入授权知识库范围，不提供外网、代码执行或任意存储访问。
- 第一版不实现 GraphRAG；只有评测证明全局/关系问题存在稳定缺口时再考虑。

## 风险与注意事项

- pgvector 列维度写入迁移后必须和 Embedding 模型一致；更换模型不能只修改环境变量。
- 对象存储与数据库没有分布式事务，需要补偿删除和孤儿对象清理。
- Worker 重试必须以 `document_id + index_version` 幂等，防止重复切片。
- 授权范围必须进入向量 SQL 查询，禁止检索后再做权限过滤。
- 文档预览、日志和错误信息不能泄露完整私有内容或供应商密钥。
- DOCX 需要限制解压体积，避免压缩炸弹。
- 中文 FTS 分词器版本变化会改变召回结果，必须作为索引版本管理并触发重建。
- 近似向量索引在权限过滤后可能召回不足，必须和精确查询定期对比。
- 文档是间接提示注入入口，任何检索内容都不能成为系统指令或工具参数来源。
- LLM Grader 和自我校验可能共同犯错，必须保留服务端引用校验和离线人工评测。
- Agentic 质量提升会增加延迟和成本，必须保留基础路径和硬预算。

## 下一步最佳动作

请下一位开发 Agent 先完整阅读：

1. `AGENTS.md`
2. `docs/PRODUCT.md`
3. `docs/ARCHITECTURE.md`
4. `session-handoff.md`

随后按“最新实施状态”中的验证顺序启动依赖并走完整链路；不要重复初始化 FBA 模板或覆盖现有 RAG 核心模块。

## 本轮变更

- 从参考看板项目的 Harness 结构重建了 RAG 项目文档。
- 将产品范围收敛到知识库、文档索引、语义检索和带来源问答。
- 按 FBA 规范定义了目录、分层、事务、响应、权限、配置和测试策略。
- 明确采用 PostgreSQL + pgvector、Celery + Redis、S3/MinIO 和供应商适配器。
- 结合当代 RAG 实践补充了上下文化父子切片、混合检索、RRF、可选重排和有界 Agentic RAG。
- 增加了严格结构化状态、只读工具、硬预算、降级、引用校验与间接提示注入防护。
- 增加了基础/Agentic 对照评测、检索/生成/引用/Agent 指标和上线门槛。
- 本轮已完成第一版工程与 RAG 核心实现、初始迁移、异步索引、混合检索、受限 Agent 编排、单元测试和运行说明。
