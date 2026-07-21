# session-handoff.md

## 当前目标

把当前可运行的 FBA RAG 基线升级为可量化、可回归、可解释的专业 AI 应用架构项目。近期重点是检索质量、索引一致性、严格测试和可观测性，不是扩大产品范围或增加开放式 Agent。

## 交接契约

本文件是下一位 Agent 开始工作的唯一“现场快照”。每次完成一个可交付切片后，必须更新：完成项及其证据、未验证项、已知风险、工作树注意事项和一个最小的下一步动作。状态含义遵循 `AGENTS.md`：没有可重复证据的实现只能记为 `implemented`，不得写成 `verified`。产品范围由 `docs/PRODUCT.md` 决定，技术契约由 `docs/ARCHITECTURE.md` 决定；本文件不应复制长期设计，也不应保留临时日志或任何敏感内容。

## 本轮 PDF 文本解析验收矩阵

| 场景 | 预期 |
|---|---|
| 文本型 PDF | `parse_document()` 返回按页分隔的正文，进入既有异步索引链路 |
| 加密 PDF | 解析失败，文档进入 `FAILED`，不尝试绕过密码 |
| 无文本层/空 PDF | 解析失败，不产生切片或 Embedding 请求 |
| 超过页数或文本字符上限 | 解析失败，限制资源消耗 |
| 其他已支持格式 | TXT、Markdown、DOCX 回归不变 |
| 用户提供的四份简历 PDF | 在本地执行只读解析冒烟，不将正文写入日志或仓库 |

## 本轮索引任务可靠性验收条件与测试矩阵

本轮只处理文档索引任务的有限重试、幂等抢占和卡住恢复，不扩展解析格式、检索策略或 Agent 图。

验收条件：

- `PENDING` 文档只能由当前 `index_version` 的任务抢占为 `PROCESSING`；重复消息不能并发生成重复切片。
- 解析错误、空文档、HTTP 400 等永久错误直接进入 `FAILED`，不自动重试。
- 网络超时、连接错误、HTTP 429 和可恢复 5xx 进入 `PENDING` 并按指数退避有限重试；超过上限后进入 `FAILED`。
- 写入 `error_message` 的内容必须脱敏，不保存模型响应体、密钥、完整文档或请求 URL。
- 超过配置时限的 `PENDING` 或 `PROCESSING` 文档由 Beat 恢复为 `PENDING` 并重新投递当前版本。
- 任务重试或恢复不得覆盖 `READY`、`DELETING` 或更新 `index_version` 后的新任务结果。

| 层级 | 场景 | 预期证据 |
|---|---|---|
| 单元 | HTTP 400、429、5xx、超时、连接错误分类 | 永久/临时错误分类断言 |
| 单元 | 重试次数与指数退避 | 次数有限，延迟不超过配置上限 |
| 单元 | 错误摘要脱敏 | 不包含响应体、URL、密钥或原始输入 |
| Service/CRUD | 当前版本 `PENDING` 抢占 | 状态变为 `PROCESSING` |
| Service/CRUD | 重复、旧版本、`READY`、`DELETING` 任务 | 不执行索引且不改变终态 |
| Service/CRUD | 永久失败、临时失败、重试耗尽 | 分别落到 `FAILED`、`PENDING`、`FAILED` |
| Celery | 临时错误触发 `retry()` | 携带当前异常、有限次数和指数退避 |
| Celery | 超时 `PENDING/PROCESSING` 修复 | 只重投递超时且未删除的当前版本 |
| 回归 | 同一消息重复投递 | 不产生重复有效切片 |

## 本轮真实 Worker/Beat 故障注入验收条件与测试矩阵

本轮只补齐真实 Redis Broker、Celery Worker 与 Beat 进程下的恢复证据，不扩展解析格式、检索策略或 Agent 图。故障注入使用独立且运行前确认为空的 Redis DB、本地受控模型端点和临时知识库；结束后清理临时数据库记录、对象与 Broker 数据。

验收条件：

- 本地模型端点超过配置的 Embedding 超时时间后，真实 Worker 将文档恢复为 `PENDING` 并有限重试；达到 `RAG_INDEX_MAX_RETRIES` 后进入 `FAILED`。
- 超时与重试耗尽轨迹只能记录文档 ID、状态、时间、任务阶段和脱敏错误摘要，不记录原始正文、密钥、请求 URL 或模型响应体。
- Worker 在文档处于 `PROCESSING` 时被强制终止后，Broker 可以重投递未确认消息；重复任务不得生成切片或覆盖当前状态。
- 真实 Beat 的修复任务将超过 `RAG_INDEX_STALE_SECONDS` 的当前版本恢复为 `PENDING` 并重新投递，新 Worker 最终将文档推进到 `READY`。
- 故障注入运行器默认不执行，只有显式设置 `RAG_RUN_CELERY_FAULT_INJECTION=1` 才能进入集成测试。

| 场景 | 预期证据 |
|---|---|
| Embedding 端点超时 | 状态轨迹包含 `PENDING -> PROCESSING -> PENDING -> PROCESSING -> FAILED`，错误摘要为脱敏超时信息 |
| Worker 中断 | 首个 Worker 在 `PROCESSING` 被终止，真实 Beat 记录至少一次恢复，新 Worker 最终写入一个有效切片并进入 `READY` |
| 幂等与清理 | 中断恢复后只有当前 `index_version` 的有效切片；临时知识库、文档、切片、Outbox、对象与独立 Broker 数据均被清理 |

## 当前状态（2026-07-21，P0 索引任务可靠性端到端验证完成）

### `verified`

- FBA API 可启动，Swagger 位于 `/docs`。
- PostgreSQL 16 + pgvector 0.8.5 与 Redis 7 通过本地 Docker 运行。
- Alembic 初始迁移已创建 `rag_knowledge_base`、`rag_document`、`rag_chunk` 和 `rag_query_log`。
- JWT 登录、创建知识库、上传 Markdown、Celery 索引到 `READY`、检索和问答完成本地端到端验证。
- DashScope `text-embedding-v4` 以 1024 维返回 Embedding，`qwen-plus` 返回带 `[S1]` 来源的答案。
- P0 评测模块实现 JSONL 数据/结果契约和 Recall@5/20、MRR、nDCG@20、引用 Precision/Recall、拒答准确率、P50/P95 指标。
- `backend/tests/rag/{unit,service,contract,evaluation}` 已建立；当前自动化套件为 42 项通过，另有 1 项需显式启用 PostgreSQL 集成环境。
- `rag_seed_v0.1.jsonl` 提供 50 条候选审阅样本，覆盖事实、术语、多跳、拒答、越权和提示注入；其状态全为 `pending_human_review`。
- Golden 评测管道已验证，2 条合成样本除 MRR 为 0.5 外其余当前指标为 1.0；它仅验证流水线，不代表领域效果。
- GitHub Actions 已配置 Ruff、Mypy、核心测试、Alembic 升级/降级和 Golden 报告 artifact。
- Alembic `20260714_0002` 的升级、降级、再升级已在本地 PostgreSQL 完成验证。
- 文档创建和重试会同事务写入 `rag_index_profile` 与 `rag_outbox_event`；`rag_dispatch_outbox` 使用锁定批量投递 Celery，避免事务内直接 `.delay()`。
- P0 回归覆盖评测阈值、私有/公开读写 SQL 范围、删除补偿、PDF 文本提取/安全拒绝和索引任务可靠性。
- `run_rag_service_evaluation.py` 可对固定数据库、用户和 `index_profile_hash` 调用真实 `QueryService` 并生成 JSONL；`evaluate_rag.py --thresholds` 可拒绝不满足版本化质量/延迟门槛的报告。
- 合成 Golden 已通过阈值门禁。其 MRR 为 0.5（拒答样本无相关切片按当前 MRR 定义记 0），不应再表述为“全部指标 1.0”。
- 文本型 PDF Parser 的单元测试通过：提取正文、拒绝加密、无文本层和错误文件签名。用户提供的四份简历 PDF 均可在本地只读解析。
- PDF 端到端冒烟已实际调用本地 API、Celery 与 DashScope：4 份简历中 1 份到达 `READY` 并生成 9 个切片，2 份在 Embedding API 返回 HTTP 400 后 `FAILED`，另 1 份在观察窗口内仍为 `PENDING`。临时账号、知识库、文档、切片、Outbox 与对象均已清理。
- 已修复索引流程未使用 `RAG_EMBEDDING_BATCH_SIZE` 的回归问题，并新增分批 Embedding 单元测试。第二次同语料验证仍有 1 份 HTTP 400、2 份 `PENDING`、1 份 `READY`；因此 PDF 全链路仍不能标记为 `verified`。第二次临时资源也已全部清理。
- 索引任务可靠性回归已验证：HTTP 400/429/5xx、超时、连接错误分类，错误摘要脱敏，有限指数退避，Celery late acknowledgement，当前版本幂等抢占，以及超时 `PENDING/PROCESSING` 恢复均有自动化断言。
- RAG 测试命令于 2026-07-20 得到 `42 passed, 1 skipped`；显式启用 PostgreSQL 合约测试后得到 `1 passed`，临时知识库和文档在事务内回滚。该合约测试验证首次抢占、重复任务拒绝和超时恢复。
- 本轮涉及的 9 个 Python 文件通过 Ruff 与格式检查，4 个业务源文件通过 mypy。
- 2026-07-21 全 RAG 范围 Ruff 与格式检查通过，Mypy 对 42 个 RAG、任务和配置源码文件检查通过。
- 核心 RAG 套件于 2026-07-21 得到 `46 passed, 2 skipped`；两个默认跳过项分别需要显式启用 PostgreSQL 与真实 Celery 故障注入环境。
- Alembic `20260714_0002` 已在专用空 PostgreSQL 数据库验证空库升级、`downgrade -1` 和从 `20260713_0001` 再升级到 head；版本与 6 张 RAG 表核对正确，临时数据库已删除。
- 真实 Worker/Beat 故障注入合约得到 `1 passed`：受控超时轨迹为 `PENDING -> PROCESSING -> PENDING -> PROCESSING -> FAILED`；Worker 在 `PROCESSING` 被强制终止后由 Beat 恢复并最终进入 `READY`，当前版本只有 1 个有效切片。
- 故障注入使用独立空闲 Redis DB、受控本地 Embedding 端点和临时业务数据，结束后知识库、文档、切片、Outbox、对象与 Broker 数据均已清理。测试专用 Beat 改用隔离持久调度文件，避免现有 `task_scheduler` 中的无关任务淹没单并发 Worker；对应回归测试已覆盖。

### `implemented`（尚未完整 `verified`）

- 知识库和文档的所有者、公开读取与管理员权限逻辑。
- TXT、Markdown、DOCX Parser，本地对象存储和文档重试/删除。
- pgvector cosine 候选、PostgreSQL FTS 候选与应用层 Reciprocal Rank Fusion（RRF）。
- HNSW cosine 索引。
- `basic`、`agentic`、`auto` 请求契约和查询日志。
- 服务端来源编号与未知引用移除。
- 删除补偿：删除 API 只标记 `DELETING` 并写 Outbox；异步任务删除对象与关联切片，Beat 定期重投递未完成删除。
- PDF 支持仅限带可提取文本层；`pypdf` Parser 已接入上传白名单，页数和正文字符数可配置。PDF 上传到 Celery、Embedding、`READY` 的端到端验证仍待补。

### `planned`

- 结构化文档中间表示、标题/页码/表格 provenance、父子切片和相邻窗口。
- 中文索引/查询一致分词、精确标识符检索与真实 `tsvector` 模型字段。
- `qwen3-rerank` Adapter、超时降级和质量/成本 A/B。
- 索引配置版本、蓝绿重建与原子切换。
- pgvector filtered ANN iterative scan 与精确召回基准。
- Worker 租约/心跳、Outbox 最大重试/告警和孤儿对象清理。
- 多节点 LangGraph：结构化路由、查询改写、有限拆解、证据判断和一次修复。
- OpenTelemetry 节点级轨迹、Token/成本统计和真实服务离线评测 CI。
- S3/MinIO Adapter 与完整 Docker 部署。

### `research`

- Late Chunking。
- ColBERT 或多向量 Late Interaction。
- GraphRAG。
- Docling PDF/表格/版面解析。
- 多模态知识库与深度研究 Agent。

研究项只有在固定错误集证明当前流水线存在稳定缺口时才能进入 `planned`。

## 当前代码事实与主要差距

1. `agent/graph.py` 只有一个 `route` 节点。它是有界状态图骨架，不是真正的多步 Agentic RAG。
2. `auto` 使用问题长度大于 80 字符的启发式规则，缺少结构化路由和评测。
3. `split_text()` 按字符和段落切分，`heading_path`、`parent_chunk_id` 与 `location` 没有真实填充。
4. 词法检索使用 PostgreSQL `simple` 配置，中文问题无法获得稳定分词召回。
5. RRF 结果没有执行配置中的最低相关度、单文档上限、父级扩展或 Rerank。
6. `score` 是 RRF 分数，不是可解释概率。API 不应把它描述为统一相关度。
7. HNSW 已创建，但没有精确检索对照、`ef_search` 调参和 filtered iterative scan 验证。
8. Outbox 已消除事务内直接投递窗口；索引 Worker 有有限重试和超时恢复，但 Dispatcher 仍无最大重试、退避、死信、可观测告警或 Worker 租约。
9. 文档删除已使用 `DELETING` + Outbox + Worker 清理对象和切片，并由 Beat 补偿重投；仍缺少孤儿对象扫描、最大重试和告警。
10. 开发 Embedding 回退在生产配置错误时会掩盖故障，需要按环境 fail closed。
11. 评测框架、真实 Service 执行器、类型检查和 CI 已建立；50 条业务候选样本尚未人工批准，固定真实报告、领域质量阈值和权限 API 集成测试尚未建立。

## 下一步开发顺序

### P0：测试与可信基线

1. 由领域负责人提供稳定、可脱敏的真实语料，将 50 条候选 JSONL 映射到真实知识库/文档/chunk 并逐条审批；再扩展至 100 条。当前仓库的 `rag_seed_v0.1.jsonl` 是占位数据，不能审批。
2. 在固定 Docker 数据库与固定 `index_profile_hash` 上运行已实现的 Service 执行器，保存不可伪造的 JSONL results。
3. 基于审批后真实报告定义并冻结 Recall、MRR/nDCG、引用、拒答与 P95 初始阈值；CI 与上一次已审批基线比较。
4. 补齐 PostgreSQL/Redis/Celery 集成环境中的 Outbox 重复投递、对象存储失败、权限 API、删除补偿和 PDF 上传至 `READY` 的端到端测试；当前为服务/SQL 契约级回归测试。
5. 排查 DashScope Embedding 对部分 PDF 提取文本的 HTTP 400：记录脱敏请求长度、批量大小、模型响应类型与失败文档特征；修复后用同一组 PDF 重跑端到端测试，并验证 `PENDING` 任务的 Worker/Beat 投递轨迹。

### P1：检索质量

1. 定义 Parser 输出的结构化中间表示，再实现标题、父子切片、页码和表格定位。
2. 为中文建立索引与查询一致的词法分析策略，并保留产品编号等精确 Token。
3. 为 HNSW 查询增加 iterative scan、过滤列索引和 exact-vs-ANN 回归测试。
4. 实现 Context Builder：来源多样性、父子去重、相邻窗口和 Token 预算。
5. 接入 `qwen3-rerank`，以 RRF 为降级路径；只有评测通过才默认开启。

### P2：真正的有界 Agentic RAG

1. 用结构化路由替换字符串长度启发式。
2. 增加查询规范化、最多 3 个子问题和并行只读检索。
3. 增加证据充分性判断、最多 2 轮检索和一次答案修复。
4. 对每个节点记录输入摘要、输出 Schema、耗时、Token、停止原因和错误类型。
5. 对比 `basic` 和 `agentic` 的复杂问题质量、P95、Token 与成本，再决定 `auto` 默认规则。

## Feature 测试门禁

每个 feature 先提交验收条件和测试矩阵。最低门禁如下：

- 单元测试覆盖纯函数、边界和异常。
- Service/CRUD 测试覆盖事务、副作用、空结果、重复请求和外部失败。
- API 测试覆盖 Schema、JWT、所有者、公开访问、管理员和越权。
- Celery 测试覆盖状态机、幂等、有限重试、重复投递与恢复。
- Alembic 测试覆盖空库升级、现有库升级和至少一次降级。
- 检索变更报告固定数据集指标、P50/P95 与相对基线变化。
- 生成/Agent 变更报告 groundedness、引用、拒答、路由、轨迹、Token 和成本。
- 安全测试覆盖提示注入、恶意文档、未知引用、越权知识库和预算耗尽。
- Bug 修复必须先添加可复现的回归测试。
- 只有全部必需门禁通过，状态才能从 `implemented` 改为 `verified`。

## 近期验收命令

当前已验证的核心测试：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
UV_CACHE_DIR=/private/tmp/rag-service-uv-cache \
uv run pytest --confcutdir=backend/tests/rag backend/tests/rag -q
```

索引状态 PostgreSQL 合约测试（临时数据自动回滚）：

```bash
RAG_RUN_POSTGRES_INTEGRATION=1 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
UV_CACHE_DIR=/private/tmp/rag-service-uv-cache \
uv run pytest --confcutdir=backend/tests/rag \
  backend/tests/rag/contract/test_index_state_postgresql.py -q
```

下一轮需要补齐并固定：

```bash
uv run ruff check backend/app/rag backend/tests/rag
uv run ruff format --check backend/app/rag backend/tests/rag
uv run pytest backend/tests/rag -q
uv run alembic upgrade head
uv run alembic downgrade -1
```

P0 新增验证命令：

```bash
uv run ruff check backend/app/rag/evaluation backend/app/rag/model/index_profile.py backend/app/rag/model/outbox_event.py backend/app/rag/service/index_profile_service.py backend/app/rag/service/outbox_service.py backend/app/task/tasks/rag/tasks.py
uv run mypy backend/app/rag/evaluation
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest --confcutdir=backend/tests/rag backend/tests/rag -q
uv run python backend/scripts/evaluate_rag.py \
  --dataset backend/tests/rag/evaluation/datasets/rag_golden_v0.1.jsonl \
  --results backend/tests/rag/evaluation/results/rag_golden_v0.1.jsonl \
  --output artifacts/rag-evaluation.json --require-approved
```

## 风险

- Embedding 维度与数据库 `vector(1024)` 是强契约，更换模型需要重建索引。
- HNSW 在知识库权限过滤后可能返回不足候选，必须启用并测试 iterative scan。
- 文档是间接提示注入入口。检索文本永远不能成为工具参数或系统指令。
- LLM-as-judge 会与被测模型共享偏差，只能作为人工标注和确定性指标的补充。
- S3/数据库/Celery 不共享事务，生产前必须实现补偿或 Outbox。
- Agentic 轮次会放大延迟、成本和攻击面。必须保留 `basic` 路径与硬预算。
- Celery 的超时重试、重试耗尽、Worker 中断和 Beat 恢复已通过本地真实进程故障注入；Dispatcher 的最大重试、退避、死信、告警和生产数据库调度器的压力验证仍未完成。
- 全 RAG 范围 Ruff、格式检查与 Mypy 已通过；RAG 范围外的全仓静态门禁本轮未执行，不能据此宣称整个 FBA 仓库无历史问题。

## 文档与研究更新

本轮已更新：

- `AGENTS.md`：增加成熟度标签、Feature 测试门禁和研究项决策规则。
- `docs/PRODUCT.md`：增加产品成功指标、当前成熟度和 P0/P1/P2/Research 路线图。
- `docs/ARCHITECTURE.md`：增加当前/目标差异、2026 检索流水线、索引 provenance、测试门禁和 ADR。
- `session-handoff.md`：移除过时清单，改为当前事实、代码差距和执行顺序。

研究依据包括 Anthropic Contextual Retrieval/Context Engineering、pgvector iterative scan、Qwen3 Embedding/Rerank、LangGraph Agentic RAG、LangSmith/RAGChecker 评测、Docling 结构化解析、Late Chunking、ColBERT、Microsoft GraphRAG 和 OWASP Agentic Top 10 2026。

## 下一步最佳动作

先完整阅读 `AGENTS.md`、`docs/PRODUCT.md`、`docs/ARCHITECTURE.md` 和本文件。随后完成 P0 的下一纵向切片：排查 DashScope Embedding 对部分 PDF 提取文本返回 HTTP 400 的原因，使用脱敏批次元数据定位失败特征，修复后以同一组 PDF 重跑上传到 `READY` 的端到端测试。不要先扩展 Agent 图。
