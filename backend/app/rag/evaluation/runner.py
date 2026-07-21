import json

from dataclasses import dataclass
from pathlib import Path

from backend.app.rag.evaluation.dataset import EvaluationCase, load_dataset
from backend.app.rag.evaluation.metrics import (
    abstention_accuracy,
    mean,
    ndcg_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
    set_precision_recall,
)


@dataclass(frozen=True)
class EvaluationResult:
    """一条离线运行结果；ID 必须来自服务端实际输出。"""

    case_id: str
    retrieved_chunk_ids: list[int]
    cited_chunk_ids: list[int]
    abstained: bool
    latency_ms: float


def load_results(path: Path) -> list[EvaluationResult]:
    """加载由集成评测执行器产生的 JSONL 结果。"""
    return [
        EvaluationResult(**json.loads(line)) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()
    ]


def build_report(*, cases: list[EvaluationCase], results: list[EvaluationResult]) -> dict[str, float | int]:
    """输出可比较的确定性质量与延迟基线。"""
    indexed = {result.case_id: result for result in results}
    missing = {case.case_id for case in cases} - indexed.keys()
    if missing:
        raise ValueError(f'缺少评测结果: {sorted(missing)}')
    recall5: list[float] = []
    recall20: list[float] = []
    mrr: list[float] = []
    ndcg: list[float] = []
    citation_precision: list[float] = []
    citation_recall: list[float] = []
    abstention: list[float] = []
    latency: list[float] = []
    for case in cases:
        result = indexed[case.case_id]
        relevant = set(case.relevant_chunk_ids)
        recall5.append(recall_at_k(ranked_ids=result.retrieved_chunk_ids, relevant_ids=relevant, k=5))
        recall20.append(recall_at_k(ranked_ids=result.retrieved_chunk_ids, relevant_ids=relevant, k=20))
        mrr.append(reciprocal_rank(ranked_ids=result.retrieved_chunk_ids, relevant_ids=relevant))
        ndcg.append(ndcg_at_k(ranked_ids=result.retrieved_chunk_ids, relevance=case.relevance, k=20))
        precision, recall = set_precision_recall(
            predicted_ids=result.cited_chunk_ids, expected_ids=case.expected_citation_chunk_ids
        )
        citation_precision.append(precision)
        citation_recall.append(recall)
        abstention.append(
            abstention_accuracy(predicted_abstain=result.abstained, expected_abstain=case.expected_abstain)
        )
        latency.append(result.latency_ms)
    return {
        'case_count': len(cases),
        'recall_at_5': mean(recall5),
        'recall_at_20': mean(recall20),
        'mrr': mean(mrr),
        'ndcg_at_20': mean(ndcg),
        'citation_precision': mean(citation_precision),
        'citation_recall': mean(citation_recall),
        'abstention_accuracy': mean(abstention),
        'latency_p50_ms': percentile(latency, 50),
        'latency_p95_ms': percentile(latency, 95),
    }


def evaluate_files(*, dataset_path: Path, results_path: Path, require_approved: bool = False) -> dict[str, float | int]:
    """评测 JSONL 数据与结果文件。"""
    return build_report(
        cases=load_dataset(dataset_path, require_approved=require_approved), results=load_results(results_path)
    )


def write_report(*, report: dict[str, float | int], output_path: Path) -> None:
    """写入稳定排序的 JSON 报告，便于 CI artifact 与基线比较。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def write_results(*, results: list[EvaluationResult], output_path: Path) -> None:
    """持久化仅由真实服务调用生成的 JSONL 运行结果。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        ''.join(json.dumps(result.__dict__, ensure_ascii=False, sort_keys=True) + '\n' for result in results),
        encoding='utf-8',
    )
