# session-handoff.md

## 当前目标

把当前可运行的 FBA RAG 基线升级为可量化、可回归、可解释的专业 AI 应用架构项目。近期重点是检索质量、索引一致性、严格测试和可观测性，不是扩大产品范围或增加开放式 Agent。

## PR #1 Rerank Python 3.11 类型修复验收矩阵（2026-07-22）

验收条件：

- GitHub Actions `quality` Job 的 Python 3.11 Mypy 命令可以稳定复现 `RAG_RERANK_BASE_URL` 未收窄和两种协议请求体推断过窄的 3 个错误。
- Adapter 必须在拼接 URL、Header 和请求体前显式校验并收窄 `base_url`、`api_key`、`model`，不能依赖 `all()` 的跨属性隐式推断。
- OpenAI 兼容与 DashScope 请求体统一声明为 `dict[str, object]`；运行时字段、降级行为和默认关闭策略不变。
- 修复后必须通过 CI 原始 Mypy 范围、Ruff、Rerank Adapter 单测和完整 RAG 测试；只有 GitHub Actions 新一轮成功后才把 PR 门禁记为 `verified`。

| 层级 | 场景 | 预期证据 |
|---|---|---|
| 静态回归 | Python 3.11 对未修复提交 `2995ad8` 执行 CI Mypy 命令 | `rerank.py:45/63/64` 共 3 个错误 |
| 类型契约 | Rerank 配置缺失 | 显式抛出既有 `ValueError`，已收窄局部变量不再为 Optional |
| 单元 | OpenAI 兼容与 DashScope 成功/失败场景 | 请求字段、用量解析和异常语义保持不变 |
| 全量门禁 | CI 原始 Ruff、Mypy 与 RAG 测试命令 | 本地全部通过；推送后 GitHub Actions `quality` 成功 |

## 公开评测网页正文提取修复验收矩阵（2026-07-21）

验收条件：

- 只从用户批准的阿里云帮助页面 `window.__ICE_PAGE_PROPS__.docDetailData.storeData.data.content` 提取正文，不索引页面脚本、导航、JSON-LD 或页脚。
- 保留标题、段落、列表和表格的确定性文本边界，使父子切片能识别章节结构。
- 页面结构缺失、正文为空、正文过短或仍含已知脚本标记时明确失败，不能生成低质量评测语料。
- 重建隔离知识库后，实际子切片数应显著低于错误基线 516，9 个批准问题的正样本应命中对应来源，两个拒答样本不得被伪标相关切片。

| 层级 | 场景 | 预期证据 |
|---|---|---|
| 单元 | 合法页面状态 JSON | 提取单份正文并保留标题/列表/表格 |
| 单元 | 导航、脚本和重复元数据 | 输出不包含 `window.pageStartTime`、`__ICE_PAGE_PROPS__`、`@context` |
| 单元 | 页面状态缺失、无正文、过短正文 | 明确 `ValueError` |
| 集成 | 3 个批准来源重建索引 | 全部 `READY`，切片不含脚本标记 |
| 评测 | 9 个批准问题 | 实际 Service 结果、真实 chunk ID、Recall/MRR/nDCG 与 P50/P95 报告 |

## 中文词法查询与精确 Token 修复验收矩阵（2026-07-21）

验收条件：

- 中文查询不能再由 `plainto_tsquery` 把全部 jieba Token 以 AND 连接并清空候选；查询词必须过滤标点和低信息单字，并限制最大数量。
- `qwen3-rerank`、`text-embedding-v4` 等带连接符的标识符必须保存为独立规范化 Token，并通过可索引的精确匹配召回，不能依赖 PostgreSQL 再次拆词后的偶然命中。
- 稠密与词法候选融合不得让 9 条批准问题相对稠密基线发生 Recall@5/20 退化；报告同时记录词法候选数、延迟和正确切片排名。
- 分词或精确 Token 配置变更必须产生新 `IndexProfile`，旧索引不能伪装成新配置的验证结果。

| 层级 | 场景 | 预期证据 |
|---|---|---|
| 单元 | 中文问句、标点、重复词、超长查询 | OR 查询无标点、去重且不超过上限 |
| 单元 | 带 `-`、`.`、`_`、`/`、`:` 的标识符 | 规范化精确 Token 完整保留 |
| Service | 稠密与词法候选有冲突 | 带权 RRF 不让通用词候选挤掉稠密第一名，精确 Token 命中可提升排序 |
| 数据库 | `exact_tokens` 数组及 GIN 索引 | 空库升级、现有库升级、降级和再升级均通过 |
| 评测 | 9 个批准问题 | 与稠密基线对比 Recall@5/20、MRR/nDCG、候选数和 P50/P95，无质量退化 |

## 真实 Rerank 接入与对比验收矩阵（2026-07-21）

验收条件：

- Adapter 同时支持 OpenAI 兼容 `/reranks` 和 DashScope `input/parameters` 协议，供应商响应统一映射为候选索引、分数与 Token 用量。
- 未启用时零远端调用；配置不完整、超时、HTTP 错误、协议错误和无效索引均降级到带权 RRF，不阻断检索。
- 真实 `qwen3-rerank` 只重排受限候选集，固定 9 条问题报告 Recall@5/20、MRR、nDCG、P50/P95、总 Token 和按官方单价估算的人民币成本。
- 只有质量不退化且延迟、成本被明确记录时才可标记真实评测通过；是否默认开启仍需基于收益决定。

| 层级 | 场景 | 预期证据 |
|---|---|---|
| 单元 | OpenAI 兼容成功响应 | 请求 `/reranks`，解析 `results` 与 `usage.total_tokens` |
| 单元 | DashScope 成功响应 | 请求服务端点，使用 `input/parameters` 并解析 `output.results` |
| 单元 | 禁用、配置缺失、HTTP/协议/索引错误 | 禁用零调用，其余明确异常并由 Query Service 安全降级 |
| 集成 | 两文档真实端点探测 | 相关文档分数高于无关文档且返回非零 Token |
| 评测 | 9 个批准问题 | 与无 Rerank 基线对比质量、延迟、Token 和成本 |

## 父级上下文、预算与拒答修复验收矩阵（2026-07-21）

验收条件：

- 父子模式下同一父节命中的多个子切片只能占用一个最终上下文位置，返回内容来自该父节且引用仍绑定实际命中的子切片。
- 问答上下文最多使用 `RAG_FINAL_CONTEXT_K` 个去重来源，并在 `RAG_CONTEXT_MAX_TOKENS` 的保守估算预算内截断，不能把 20 个完整父节无界传给模型。
- 问题明确要求“本项目/本系统/本服务/我们的”范围，而来源没有同范围证据时，必须返回 `insufficient_evidence` 且不附带伪引用。
- 离线执行器只能统计答案文本实际出现且由服务端签发的 `[S数字]`，不能把全部检索来源伪算为引用。

| 层级 | 场景 | 预期证据 |
|---|---|---|
| 单元 | 同父节多个命中 | 最终来源只保留最高排名子切片，父节内容只出现一次 |
| 单元 | 来源数和 Token 预算耗尽 | 有界选择与确定性截断，引用序号保持有效 |
| 单元 | 本项目范围有/无同范围证据 | 分别继续回答/拒答 |
| 单元 | 已知、未知和未出现的引用 | 只保留实际出现的已知来源 ID |
| 评测 | 9 个批准问题的 basic answer | 两个范围外问题拒答，正样本报告实际引用、延迟和模型用量 |

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

### PDF Embedding HTTP 400 修复验收矩阵（2026-07-21）

| 层级 | 场景 | 预期 |
|---|---|---|
| 单元 | 多条文本 Embedding 返回 HTTP 400 | 二分拆批，保持向量顺序；不使用本地向量回退 |
| 单元 | 单条文本仍返回 HTTP 400 | 明确抛出异常，Celery 沿用永久失败语义 |
| 回归 | PDF 提取文本含 `NUL` 或其他不可持久化控制字符 | Parser 在写入 PostgreSQL 前统一清洗，保留合法分页正文 |
| 诊断 | 四份简历 PDF 的每个原始批次 | 只输出文件名、批次大小、字符统计和结果，不输出正文或密钥 |
| 端到端 | 上传同一组 PDF | API、Outbox、Celery 后全部成为 `READY`，每份有非零切片；临时资源清理 |

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

## 当前状态（2026-07-22，PDF 与公开代理集验证完成）

### `verified`

- 公开网页正文提取器只解析阿里云页面状态中的 `docDetailData.storeData.data.content`，保留标题、列表和表格并拒绝缺失、过短或含脚本噪声的正文；3 份批准来源重建后均为 `READY`，子切片数为 `95/11/39`，不再使用错误的 516 切片噪声索引。
- 用户批准的公开代理集 `public_rag_v0.1` 含 3 份公开中文 RAG 文档和 9 条问题，绑定本地隔离知识库 `23` 与 profile `477acef1d1b5da8655f32d42f4428e3fc0ff5b4f2723a8df90bd5bf4022c5fdf`。它可验证实现，但不是领域负责人审批的 50 到 100 条业务发布基线。
- 中文词法修复已验证：受限 OR 查询不再产生 9/9 空候选，连接符标识符进入 `exact_tokens TEXT[]` + GIN；`qwen3-rerank` 和 `text-embedding-v4` 分别精确命中 6/8 个切片。dense-only 与混合检索的 Recall@5/20、MRR、nDCG 均为 `1.0`；单次小样本延迟仅记录观测值，不宣称性能提升。
- 父子切片与 Context Builder 已验证为可选能力：父节不参与召回，同父节去重，问答最多使用 8 个来源并受 6000 Token 保守预算限制。parent 对 child 的 citation precision 为 `0.6426` 对 `0.5963`，但输入 Token 为 `24354` 对 `14451`、估算成本为 `¥0.0233592` 对 `¥0.0157688`，证据不足以默认启用，`RAG_PARENT_CONTEXT_ENABLED=false`。
- 范围证据与引用统计已验证：9 条 basic answer 中两个“本项目”范围外问题均拒答，拒答准确率 `1.0`；7 次 Chat 全部成功，citation recall `1.0`，precision `0.6426`。precision 未满是因为答案引用了 Golden 未列出的其他来源，不修改 Golden 粉饰结果。
- OpenAI 兼容和 DashScope Rerank 协议、用量采集与 RRF 降级已验证。真实 `qwen3-rerank` 9/9 成功，消耗 `120434` Token、按 `¥0.5/百万 Token` 估算 `¥0.060217`；但 Recall@5/20 从 `1.0` 降为 `0.8571`、MRR 降为 `0.6548`、P50 从约 `405 ms` 增为 `1031 ms`，所以 `RAG_RERANK_ENABLED=false`。
- 评测报告位于 `artifacts/public-rag-v0.1.*.json`，真实 Service results 位于 `backend/tests/rag/evaluation/results/public_rag_v0.1*.jsonl`；retrieval-only 报告不再伪造引用/拒答指标，answer 报告只统计答案中实际出现的已知 `[S数字]`。
- PDF 真实闭环已验证：4 份文本型 PDF 经本地 API、Outbox、Celery Worker 和 DashScope Embedding 后 4/4 进入 `READY`；检索返回 5 个来源，basic 问答状态为 `answered` 并返回 5 个服务端来源。验证只保留计数与状态，不记录简历正文；临时用户和文档均已清理，知识库按软删除契约仅保留无关联数据的墓碑。
- PDF 失败根因已回归覆盖：其中一份提取文本含 `NUL`，asyncpg 在持久化 `parsed_content` 时拒绝 PostgreSQL UTF-8 文本；所有 Parser 现在复用 `clean_text()` 在持久化前移除 `NUL` 和不可接受控制字符。Embedding HTTP 400 仍保留二分拆批保护，单条失败继续 fail closed。
- 当前全 RAG 套件为 `70 passed, 2 skipped`；显式 PostgreSQL 状态合约为 `1 passed`。Ruff、格式检查与 CI 同范围 Mypy（46 个源码文件）通过。
- PR #1 的 Python 3.11 类型回归已在隔离的 CPython 3.11.14 环境验证：未修复提交 `2995ad8` 的 GitHub Actions 日志稳定报告 `rerank.py:45/63/64` 三个错误；修复后 CI 原始 Mypy 命令为 `Success: no issues found in 46 source files`，Rerank 专项 `5 passed`，全 RAG 套件 `70 passed, 2 skipped`，Alembic 往返与 Golden 阈值命令通过。运行时请求协议和默认开关未改变。
- Alembic `20260721_0004` 已验证开发现有库 `0003 -> 0004 -> 0003 -> 0004`；专用空库从初始迁移升级到 `0004` 后核对 `exact_tokens` 数组与 GIN 索引，临时数据库已删除。

- FBA API 可启动，Swagger 位于 `/docs`。
- PostgreSQL 16 + pgvector 0.8.5 与 Redis 7 通过本地 Docker 运行。
- Alembic 初始迁移已创建 `rag_knowledge_base`、`rag_document`、`rag_chunk` 和 `rag_query_log`。
- JWT 登录、创建知识库、上传 Markdown、Celery 索引到 `READY`、检索和问答完成本地端到端验证。
- DashScope `text-embedding-v4` 以 1024 维返回 Embedding，`qwen-plus` 返回带 `[S1]` 来源的答案。
- P0 评测模块实现 JSONL 数据/结果契约和 Recall@5/20、MRR、nDCG@20、引用 Precision/Recall、拒答准确率、P50/P95 指标。
- `backend/tests/rag/{unit,service,contract,evaluation}` 已建立；默认套件和需显式启用的 PostgreSQL、真实 Celery 合约分别保留清晰边界。
- `rag_seed_v0.1.jsonl` 提供 50 条候选审阅样本，覆盖事实、术语、多跳、拒答、越权和提示注入；其状态全为 `pending_human_review`。
- Golden 评测管道已验证，2 条合成样本的当前确定性指标均为 1.0；它仅验证流水线，不代表领域效果。
- GitHub Actions 已配置 Ruff、Mypy、核心测试、Alembic 升级/降级和 Golden 报告 artifact。
- Alembic `20260714_0002` 的升级、降级、再升级已在本地 PostgreSQL 完成验证。
- 文档创建和重试会同事务写入 `rag_index_profile` 与 `rag_outbox_event`；`rag_dispatch_outbox` 使用锁定批量投递 Celery，避免事务内直接 `.delay()`。
- P0 回归覆盖评测阈值、私有/公开读写 SQL 范围、删除补偿、PDF 文本提取/安全拒绝和索引任务可靠性。
- `run_rag_service_evaluation.py` 可对固定数据库、用户和 `index_profile_hash` 调用真实 `QueryService` 并生成 JSONL；`evaluate_rag.py --thresholds` 可拒绝不满足版本化质量/延迟门槛的报告。
- 合成 Golden 已通过阈值门禁。检索排名指标只统计有相关切片的正样本，拒答样本进入拒答准确率，因此当前 MRR 为 1.0；该口径仍不代表领域质量。
- 文本型 PDF Parser 的单元测试通过：提取正文、拒绝加密、无文本层、错误文件签名与 `NUL` 清洗。用户提供的四份简历 PDF 均完成真实异步索引闭环，而不再只停留在只读解析冒烟。
- 历史 PDF 失败先后暴露了 Embedding 批次 HTTP 400 和提取文本 `NUL` 两类独立问题。当前实现分别以 HTTP 400 二分拆批和 Parser 统一文本清洗修复；最终同组 4 份 PDF 已全部 `READY`，历史失败不能再描述为当前状态。
- 索引任务可靠性回归已验证：HTTP 400/429/5xx、超时、连接错误分类，错误摘要脱敏，有限指数退避，Celery late acknowledgement，当前版本幂等抢占，以及超时 `PENDING/PROCESSING` 恢复均有自动化断言。
- PostgreSQL 合约测试验证首次抢占、重复任务拒绝和超时恢复；临时知识库和文档在事务内回滚。
- Alembic `20260714_0002` 已在专用空 PostgreSQL 数据库验证空库升级、`downgrade -1` 和从 `20260713_0001` 再升级到 head；版本与 6 张 RAG 表核对正确，临时数据库已删除。
- 真实 Worker/Beat 故障注入合约得到 `1 passed`：受控超时轨迹为 `PENDING -> PROCESSING -> PENDING -> PROCESSING -> FAILED`；Worker 在 `PROCESSING` 被强制终止后由 Beat 恢复并最终进入 `READY`，当前版本只有 1 个有效切片。
- 故障注入使用独立空闲 Redis DB、受控本地 Embedding 端点和临时业务数据，结束后知识库、文档、切片、Outbox、对象与 Broker 数据均已清理。测试专用 Beat 改用隔离持久调度文件，避免现有 `task_scheduler` 中的无关任务淹没单并发 Worker；对应回归测试已覆盖。
- 真实全链路 E2E 已验证（2026-08-01，连续两次通过，其中一次经 `RAG_RUN_REAL_E2E=1 pytest backend/tests/rag/contract/test_real_rag_e2e.py` 为 `1 passed`，63.5s）：`run_rag_e2e.py` 自行拉起 uvicorn API + Celery Worker/Beat（隔离空闲 Redis Broker DB，`RAG_ALLOW_LOCAL_MODEL_FALLBACK=false` 关闭本地回退），经 HTTP 完成登录 → 建库 → 上传 Markdown → Outbox → Celery → 真实 DashScope Embedding → `READY`（5 切片）→ 混合检索命中目标切片（top score `0.02459`，与加权 RRF 上限分析吻合）→ 真实 `qwen-plus` 两问均正确作答并带 `[S1]` 引用 → 51 个 `knowledge_base_ids` 被 422 拒绝 → 异步删除（Outbox → Worker 行锁路径）完成、知识库删除成功。运行环境为 main 合并 PR #4/#5/#6/#7 的组合（#7 修复启动阻断、#5 提供入参上限）；观察项：库外问题状态仍为 `answered`（无相关度下限缺陷复现，模型自行答复“资料中未提供”）。

- 模型回退策略改为 fail-closed：新增 `RAG_ALLOW_LOCAL_MODEL_FALLBACK`（默认 `true`），`Settings.check_env` 在 `ENVIRONMENT=prod` 时强制为 `false`；Embedding 与 Chat 适配器在回退被禁止时抛 `errors.ServerError`，允许回退时记录 WARNING。配置层策略与适配层执行各有单元测试（全量套件 `78 passed, 2 skipped`）。仍为 `implemented`：只有单元级 fake 证据，缺少生产配置下的可重复端到端验证，也未处理历史伪向量切片的标记与重建。

- `public_rag_v0.1` 的 chunk ID 绑定本地隔离数据库；仓库保存来源清单、问题、results 和报告，但未提交公开网页正文或可自动重建的索引快照，因此跨环境复跑前必须按来源清单重新提取、索引并重新核对 ID。
- 50 条 `rag_seed_v0.1` 业务候选仍为 `pending_human_review`；没有领域负责人提供的脱敏语料和逐条审批，不能把 9 条公开代理集升级为业务发布阈值。

- 知识库和文档的所有者、公开读取与管理员权限逻辑。文档重试与删除已修正为写权限范围：`DocumentService.get` 增加仅关键字 `write` 参数并透传给 `knowledge_base_dao.get_authorized`，`retry` 与 `delete` 以 `write=True` 校验，非所有者对公开知识库的重试/删除由 200 变为 404；`get_list`、`get_chunks` 与文档详情仍为读范围。仍为 `implemented`：回归测试以 fake 替换 `KnowledgeBaseService.get`，只锁定了调用方传参与 DAO 谓词两端，尚未覆盖 Service 到 DAO 的 `write` 透传本身，也没有端到端权限 API 集成测试。
- TXT、Markdown、DOCX Parser，本地对象存储和文档重试/删除。
- pgvector cosine 候选、PostgreSQL FTS 候选与应用层 Reciprocal Rank Fusion（RRF）。
- HNSW cosine 索引。
- `basic`、`agentic`、`auto` 请求契约和查询日志。
- 服务端来源编号与未知引用移除。
- 删除补偿：删除 API 只标记 `DELETING` 并写 Outbox；异步任务删除对象与关联切片，Beat 定期重投递未完成删除。
- PDF 支持仅限带可提取文本层；`pypdf` Parser 已接入上传白名单，页数和正文字符数可配置，文本型 PDF 上传到 Celery、Embedding、`READY` 的端到端验证已通过。OCR 与复杂版面仍不在当前能力内。

### `planned`

- 结构化文档中间表示、标题/页码/表格 provenance 和相邻窗口。
- 索引配置版本、蓝绿重建与原子切换。
- pgvector filtered ANN iterative scan 与精确召回基准。
- Worker 租约/心跳、Outbox 最大重试/告警和孤儿对象清理。
- 多节点 LangGraph：结构化路由、查询改写、有限拆解、证据判断和一次修复。
- OpenTelemetry 节点级轨迹和真实服务离线评测 CI。
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
3. `location` 尚未记录精确页内字符范围；父子上下文扩展当前以 Markdown 标题和 PDF 页标记为边界，表格和复杂版面仍需要结构化 Parser。
4. 中文分词与精确 Token 已在公开固定代理集证明不退化，但尚未在领域业务集证明收益；PostgreSQL 仍使用 `simple` 配置而非原生中文词法分析器。
5. 父级扩展已有同父节去重、来源数和 Token 预算；仍缺少相邻窗口、跨文档多样性配额与可校准最低分。
6. `score` 是 RRF 分数，不是可解释概率。API 不应把它描述为统一相关度。
7. HNSW 已创建，但没有精确检索对照、`ef_search` 调参和 filtered iterative scan 验证。
8. Outbox 已消除事务内直接投递窗口；索引 Worker 有有限重试和超时恢复，但 Dispatcher 仍无最大重试、退避、死信、可观测告警或 Worker 租约。
9. 文档删除已使用 `DELETING` + Outbox + Worker 清理对象和切片，并由 Beat 补偿重投；仍缺少孤儿对象扫描、最大重试和告警。
10. 模型回退已由 `RAG_ALLOW_LOCAL_MODEL_FALLBACK` 显式控制，`ENVIRONMENT=prod` 时 `check_env` 强制关闭，未配置即抛 `ServerError`；回退启用时每次调用记录 WARNING。残留风险：`get_settings()` 在缺少 `.env` 时会复制 `ENVIRONMENT='dev'` 的 `.env.example`，因此沿用 dev 配置的生产主机仍会回退，只能靠显式设为 false 与 WARNING 发现；历史上已用伪向量写入的切片没有 provenance 标记，无法定位重建。
11. 评测框架、公开代理报告、真实 Service 执行器、类型检查和 CI 已建立；50 条业务候选样本尚未人工批准，领域质量阈值和权限 API 集成测试尚未建立。

## 下一步开发顺序

### P0：测试与可信基线

1. 由领域负责人提供稳定、可脱敏的真实语料，将 50 条候选 JSONL 映射到真实知识库/文档/chunk 并逐条审批；再扩展至 100 条。当前仓库的 `rag_seed_v0.1.jsonl` 是占位数据，不能审批。
2. 在固定 Docker 数据库与固定 `index_profile_hash` 上运行已实现的 Service 执行器，保存不可伪造的 JSONL results。
3. 基于审批后真实报告定义并冻结 Recall、MRR/nDCG、引用、拒答与 P95 初始阈值；CI 与上一次已审批基线比较。
4. 补齐 PostgreSQL/Redis/Celery 集成环境中的 Outbox 重复投递、对象存储失败、权限 API 和删除补偿端到端测试；PDF 上传至 `READY` 已完成真实闭环验证。

### P1：检索质量

1. 领域负责人提供并人工审批真实、可脱敏语料后，复用已验证执行器复跑父子、中文词法和 Rerank；公开代理结论不能替代业务发布门槛。
2. 定义结构化 Parser 中间表示，补齐表格、页内位置和复杂标题层级。
3. 为 HNSW 查询增加 iterative scan、过滤列索引和 exact-vs-ANN 回归测试。
4. 扩展 Context Builder：相邻窗口、跨文档多样性配额和可校准最低分。
5. 保留 `qwen3-rerank` 默认关闭；只有领域评测证明相对 RRF 有收益才重新考虑启用。

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

先完整阅读 `AGENTS.md`、`docs/PRODUCT.md`、`docs/ARCHITECTURE.md` 和本文件。下一纵向切片应等待领域负责人提供稳定、可脱敏的真实业务语料与逐条审批结果，再用已验证执行器冻结 50 到 100 条业务发布基线；在输入到位前，可独立补齐权限 API、Outbox 重复投递、对象存储失败和删除补偿的集成门禁。不要把 9 条公开代理集写成领域发布基线，也不要先扩展 Agent 图。
