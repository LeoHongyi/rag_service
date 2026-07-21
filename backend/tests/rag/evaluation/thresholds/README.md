# RAG 质量阈值

`rag_golden_v0.1.json` 只约束合成 Golden fixture 的评测管道，不是业务质量阈值。

生成真实发布阈值前必须满足：

1. 使用固定 Docker PostgreSQL 数据库和真实、稳定的知识库/文档。
2. 使用 `run_rag_service_evaluation.py`，并传入本次索引的 `index_profile_hash`。
3. 数据集每条记录的 `review_status` 都由领域负责人改为 `approved`。
4. 审核人基于实际文档确认问题、相关切片、引用与拒答预期。
5. 将真实报告中的首个基线值、可接受回退和 P95 预算写入新的版本化 JSON 文件。

禁止把候选队列、合成 Golden 或手工伪造的 result JSONL 用作业务发布门槛。
