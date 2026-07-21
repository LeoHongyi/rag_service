import json

from pathlib import Path

import pytest

from backend.app.rag.evaluation.thresholds import assert_report_meets_thresholds, load_thresholds


def test_thresholds_reject_quality_regression(tmp_path: Path) -> None:
    path = tmp_path / 'thresholds.json'
    path.write_text(
        json.dumps({
            'dataset_version': 'rag-real-v0.1',
            'index_profile_hash': 'a' * 64,
            'thresholds': [
                {'metric': 'recall_at_5', 'comparator': 'min', 'value': 0.8},
                {'metric': 'latency_p95_ms', 'comparator': 'max', 'value': 100.0},
            ],
        }),
        encoding='utf-8',
    )
    thresholds = load_thresholds(path)
    assert_report_meets_thresholds(report={'recall_at_5': 0.8, 'latency_p95_ms': 100}, thresholds=thresholds)
    with pytest.raises(ValueError, match='recall_at_5'):
        assert_report_meets_thresholds(report={'recall_at_5': 0.79, 'latency_p95_ms': 80}, thresholds=thresholds)
