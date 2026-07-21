from pathlib import Path

from backend.app.rag.evaluation.dataset import load_dataset


def test_seed_dataset_has_required_p0_coverage() -> None:
    cases = load_dataset(Path('backend/tests/rag/evaluation/datasets/rag_seed_v0.1.jsonl'))
    assert len(cases) == 50
    assert {'fact', 'terminology', 'multi_hop', 'abstention', 'authorization', 'prompt_injection'} <= {
        case.category for case in cases
    }
    assert all(case.review_status == 'pending_human_review' for case in cases)
