import asyncio

from types import SimpleNamespace
from typing import Any

from pytest import MonkeyPatch

from backend.app.rag.evaluation.dataset import EvaluationCase
from backend.app.rag.evaluation.service_executor import run_service_evaluation


def test_service_executor_uses_query_service_output(monkeypatch: MonkeyPatch) -> None:
    case = EvaluationCase(
        case_id='real-service-contract',
        question='测试问题',
        category='fact',
        knowledge_base_ids=[3],
        relevant_chunk_ids=[9],
        relevance={9: 2},
        expected_citation_chunk_ids=[9],
        expected_abstain=False,
        review_status='approved',
    )

    async def fake_profile(**_kwargs: Any) -> None:
        await asyncio.sleep(0)

    async def fake_retrieve(**kwargs: Any) -> list[SimpleNamespace]:
        await asyncio.sleep(0)
        assert kwargs['obj'].knowledge_base_ids == [3]
        assert kwargs['obj'].top_k == 20
        return [SimpleNamespace(chunk_id=9)]

    monkeypatch.setattr('backend.app.rag.evaluation.service_executor.assert_index_profile_available', fake_profile)
    monkeypatch.setattr('backend.app.rag.evaluation.service_executor.QueryService.retrieve', fake_retrieve)

    results = asyncio.run(
        run_service_evaluation(
            db=object(),
            cases=[case],
            user_id=1,
            is_admin=False,
            index_profile_hash='a' * 64,
        )
    )

    assert results[0].case_id == case.case_id
    assert results[0].retrieved_chunk_ids == [9]
    assert not results[0].abstained
