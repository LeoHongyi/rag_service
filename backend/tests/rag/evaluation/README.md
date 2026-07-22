# RAG 离线评测集

`rag_seed_v0.1.jsonl` 含 50 条候选标注，覆盖事实、术语、多跳、拒答、越权与提示注入。它是可导入的**审阅队列**，不是已完成的人工基线：每条数据必须由领域负责人验证问题、授权知识库、相关 `chunk_id`、引用集合和拒答预期后，才可将 `review_status` 改为 `approved`。

评测运行器在带 `--require-approved` 时会拒绝任何未审批样本。真实运行结果以 JSONL 保存，每行格式如下：

```json
{"case_id":"seed-001","retrieved_chunk_ids":[1,2],"cited_chunk_ids":[1],"abstained":false,"latency_ms":12.4}
```

不要手工伪造 result 文件作为质量证明；它必须由固定索引、固定服务版本的集成执行器生成。每次变更检索、生成、模型、分词或切分时，保存数据集版本、索引 profile hash、Git SHA 与报告。

真实服务执行器示例：

```bash
uv run python backend/scripts/run_rag_service_evaluation.py \
  --dataset path/to/approved-real-v0.1.jsonl \
  --output artifacts/approved-real-v0.1.results.jsonl \
  --index-profile-hash <固定索引配置哈希> \
  --user-id <评测专用用户 ID> \
  --require-approved

uv run python backend/scripts/evaluate_rag.py \
  --dataset path/to/approved-real-v0.1.jsonl \
  --results artifacts/approved-real-v0.1.results.jsonl \
  --output artifacts/approved-real-v0.1.report.json \
  --require-approved \
  --thresholds path/to/approved-real-v0.1.thresholds.json
```

`rag_seed_v0.1.jsonl` 是占位审阅队列，不能绑定到实际数据库，也绝不能改为 `approved`。领域负责人必须提供稳定、可脱敏的语料和人工审核结果；随后才能建立真实版本的 JSONL 与质量阈值。

`candidates/public_rag_sources_v0.1.json` 是公开中文技术资料的候选来源及待审问题。它只保存 URL、来源元数据与问题，不保存网页正文；在审阅人确认来源可用于内部评测、上传后映射真实切片并逐题审批之前，不得将其转换为 `approved` JSONL。
