import operator

from collections.abc import Iterable, Sequence
from math import log2


def recall_at_k(*, ranked_ids: Sequence[int], relevant_ids: set[int], k: int) -> float:
    """计算单条查询的 Recall@K。"""
    if not relevant_ids:
        return 1.0
    return len(set(ranked_ids[:k]) & relevant_ids) / len(relevant_ids)


def reciprocal_rank(*, ranked_ids: Sequence[int], relevant_ids: set[int]) -> float:
    """计算单条查询的倒数排名。"""
    for rank, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(*, ranked_ids: Sequence[int], relevance: dict[int, int], k: int) -> float:
    """计算支持分级相关性的 nDCG@K。"""

    def dcg(ids: Sequence[int]) -> float:
        return sum(
            (2 ** relevance.get(chunk_id, 0) - 1) / log2(rank + 1) for rank, chunk_id in enumerate(ids[:k], start=1)
        )

    actual = dcg(ranked_ids)
    ideal = dcg([chunk_id for chunk_id, _score in sorted(relevance.items(), key=operator.itemgetter(1), reverse=True)])
    return actual / ideal if ideal else 1.0


def set_precision_recall(*, predicted_ids: Iterable[int], expected_ids: Iterable[int]) -> tuple[float, float]:
    """计算确定性来源集合的 Precision / Recall。"""
    predicted = set(predicted_ids)
    expected = set(expected_ids)
    if not predicted:
        return (1.0 if not expected else 0.0, 1.0 if not expected else 0.0)
    overlap = len(predicted & expected)
    return overlap / len(predicted), overlap / len(expected) if expected else 1.0


def abstention_accuracy(*, predicted_abstain: bool, expected_abstain: bool) -> float:
    """计算单条拒答判断是否正确。"""
    return float(predicted_abstain == expected_abstain)


def mean(values: Sequence[float]) -> float:
    """计算非空序列均值。"""
    if not values:
        raise ValueError('指标样本不能为空')
    return sum(values) / len(values)


def percentile(values: Sequence[float], percentile_value: int) -> float:
    """使用 nearest-rank 计算 P50/P95，避免额外数值依赖。"""
    if not values:
        raise ValueError('延迟样本不能为空')
    if not 0 < percentile_value <= 100:
        raise ValueError('percentile 必须在 1 到 100 之间')
    ordered = sorted(values)
    index = max(0, (len(ordered) * percentile_value + 99) // 100 - 1)
    return ordered[index]
