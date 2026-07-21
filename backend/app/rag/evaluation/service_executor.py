"""使用真实 RAG Service 生成离线评测运行结果。"""

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rag.evaluation.dataset import EvaluationCase
from backend.app.rag.evaluation.runner import EvaluationResult
from backend.app.rag.model import Document, IndexProfile
from backend.app.rag.schema.query import AnswerParam, RetrieveParam
from backend.app.rag.service.query_service import QueryService


async def assert_index_profile_available(*, db: AsyncSession, profile_hash: str) -> None:
    """确保执行器显式绑定到已经存在的不可变索引配置。"""
    profile_id = await db.scalar(
        select(IndexProfile.id).where(IndexProfile.profile_hash == profile_hash, IndexProfile.deleted == 0)
    )
    if profile_id is None:
        raise ValueError('指定的 index_profile_hash 不存在')
    document_id = await db.scalar(
        select(Document.id).where(Document.index_profile_id == profile_id, Document.deleted == 0).limit(1)
    )
    if document_id is None:
        raise ValueError('指定索引配置下没有可评测文档')


async def run_service_evaluation(
    *,
    db: AsyncSession,
    cases: list[EvaluationCase],
    user_id: int,
    is_admin: bool,
    index_profile_hash: str,
    answer_mode: str | None = None,
) -> list[EvaluationResult]:
    """通过真实 Service 调用生成结果，禁止手工填写检索或引用 ID。"""
    await assert_index_profile_available(db=db, profile_hash=index_profile_hash)
    results: list[EvaluationResult] = []
    for case in cases:
        started = time.perf_counter()
        if answer_mode is None:
            sources = await QueryService.retrieve(
                db=db,
                user_id=user_id,
                is_admin=is_admin,
                obj=RetrieveParam(question=case.question, knowledge_base_ids=case.knowledge_base_ids, top_k=20),
            )
            results.append(
                EvaluationResult(
                    case_id=case.case_id,
                    retrieved_chunk_ids=[source.chunk_id for source in sources],
                    cited_chunk_ids=[],
                    abstained=not sources,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
            continue
        answer = await QueryService.answer(
            db=db,
            user_id=user_id,
            is_admin=is_admin,
            obj=AnswerParam(
                question=case.question,
                knowledge_base_ids=case.knowledge_base_ids,
                top_k=20,
                mode=answer_mode,
            ),
        )
        results.append(
            EvaluationResult(
                case_id=case.case_id,
                retrieved_chunk_ids=[source.chunk_id for source in answer.sources],
                cited_chunk_ids=[source.chunk_id for source in answer.sources],
                abstained=answer.status == 'insufficient_evidence',
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        )
    return results
