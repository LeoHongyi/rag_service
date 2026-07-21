import json

from pathlib import Path

import pytest

from backend.app.rag.evaluation.dataset import load_dataset
from backend.app.rag.evaluation.runner import evaluate_files


def test_runner_builds_complete_report(tmp_path: Path) -> None:
    dataset = tmp_path / 'dataset.jsonl'
    results = tmp_path / 'results.jsonl'
    dataset.write_text(
        json.dumps({
            'case_id': 'c1',
            'question': 'q',
            'category': 'fact',
            'knowledge_base_ids': [1],
            'relevant_chunk_ids': [2],
            'relevance': {'2': 2},
            'expected_citation_chunk_ids': [2],
            'expected_abstain': False,
            'review_status': 'approved',
        })
        + '\n',
        encoding='utf-8',
    )
    results.write_text(
        json.dumps({
            'case_id': 'c1',
            'retrieved_chunk_ids': [2],
            'cited_chunk_ids': [2],
            'abstained': False,
            'latency_ms': 7.0,
        })
        + '\n',
        encoding='utf-8',
    )
    report = evaluate_files(dataset_path=dataset, results_path=results, require_approved=True)
    assert report['recall_at_5'] == pytest.approx(1.0)
    assert report['citation_precision'] == pytest.approx(1.0)
    assert report['latency_p95_ms'] == pytest.approx(7.0)


def test_approved_gate_rejects_candidate_dataset() -> None:
    with pytest.raises(ValueError, match='尚未人工审批'):
        load_dataset(Path('backend/tests/rag/evaluation/datasets/rag_seed_v0.1.jsonl'), require_approved=True)
