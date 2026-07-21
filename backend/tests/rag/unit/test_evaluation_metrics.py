import pytest

from backend.app.rag.evaluation.metrics import (
    abstention_accuracy,
    ndcg_at_k,
    percentile,
    recall_at_k,
    reciprocal_rank,
    set_precision_recall,
)


def test_retrieval_metrics_use_rank_and_relevance() -> None:
    ranked = [9, 2, 1]
    relevant = {1, 2}
    assert recall_at_k(ranked_ids=ranked, relevant_ids=relevant, k=2) == pytest.approx(0.5)
    assert reciprocal_rank(ranked_ids=ranked, relevant_ids=relevant) == pytest.approx(0.5)
    assert ndcg_at_k(ranked_ids=[2, 1], relevance={1: 1, 2: 3}, k=2) == pytest.approx(1.0)


def test_citation_and_abstention_metrics_are_deterministic() -> None:
    assert set_precision_recall(predicted_ids=[1, 3], expected_ids=[1, 2]) == (0.5, 0.5)
    assert abstention_accuracy(predicted_abstain=True, expected_abstain=True) == pytest.approx(1.0)
    assert percentile([1, 2, 3, 4, 5], 95) == 5
