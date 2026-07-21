import time
import uuid

from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rag.adapters.embedding import embedding_provider
from backend.app.rag.adapters.llm import chat_provider
from backend.app.rag.agent.graph import agent_graph
from backend.app.rag.enums import DocumentStatus
from backend.app.rag.model import Chunk, Document, KnowledgeBase, QueryLog
from backend.app.rag.schema.query import AnswerParam, GetAnswerDetail, GetSourceDetail, RetrieveParam
from backend.common.exception import errors
from backend.core.conf import settings


class _MergedResult(TypedDict):
    chunk: Chunk
    name: str
    score: float
    dense: float


class QueryService:
    @staticmethod
    async def _accessible_kb_ids(db: AsyncSession, *, user_id: int, is_admin: bool, requested: list[int]) -> list[int]:
        stmt = select(KnowledgeBase.id).where(KnowledgeBase.id.in_(requested), KnowledgeBase.deleted == 0)
        if not is_admin:
            stmt = stmt.where((KnowledgeBase.owner_id == user_id) | KnowledgeBase.is_public)
        ids = list((await db.scalars(stmt)).all())
        if not ids:
            raise errors.NotFoundError(msg='没有可访问的知识库')
        return ids

    @staticmethod
    async def retrieve(*, db: AsyncSession, user_id: int, is_admin: bool, obj: RetrieveParam) -> list[GetSourceDetail]:
        ids = await QueryService._accessible_kb_ids(
            db, user_id=user_id, is_admin=is_admin, requested=obj.knowledge_base_ids
        )
        vector = (await embedding_provider.embed([obj.question]))[0]
        base = (
            select(Chunk, Document.filename)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.knowledge_base_id.in_(ids),
                Chunk.deleted == 0,
                Document.status == DocumentStatus.READY,
                Document.deleted == 0,
            )
        )
        distance = Chunk.embedding.cosine_distance(vector).label('distance')
        dense_rows = (
            await db.execute(base.add_columns(distance).order_by(distance).limit(settings.RAG_DENSE_CANDIDATE_K))
        ).all()

        # PostgreSQL full-text candidate set.  RRF happens in Python so both
        # rank lists remain independently inspectable and portable to rerankers.
        tsquery = func.websearch_to_tsquery('simple', obj.question)
        lexical_rank = func.ts_rank_cd(func.to_tsvector('simple', Chunk.search_text), tsquery).label('lexical_rank')
        lexical_rows = (
            await db.execute(
                base
                .add_columns(lexical_rank)
                .where(func.to_tsvector('simple', Chunk.search_text).op('@@')(tsquery))
                .order_by(lexical_rank.desc())
                .limit(settings.RAG_LEXICAL_CANDIDATE_K)
            )
        ).all()

        merged: dict[int, _MergedResult] = {}
        for rank, (chunk, name, value) in enumerate(dense_rows, 1):
            merged[chunk.id] = {
                'chunk': chunk,
                'name': name,
                'score': 1 / (settings.RAG_RRF_K + rank),
                'dense': max(0.0, 1 - float(value)),
            }
        for rank, (chunk, name, _value) in enumerate(lexical_rows, 1):
            item = merged.setdefault(chunk.id, {'chunk': chunk, 'name': name, 'score': 0.0, 'dense': 0.0})
            item['score'] = float(item['score']) + 1 / (settings.RAG_RRF_K + rank)

        ordered = sorted(merged.values(), key=lambda item: float(item['score']), reverse=True)[: obj.top_k]
        return [
            GetSourceDetail(
                knowledge_base_id=item['chunk'].knowledge_base_id,
                document_id=item['chunk'].document_id,
                document_name=str(item['name']),
                chunk_id=item['chunk'].id,
                chunk_index=item['chunk'].chunk_index,
                content=item['chunk'].content,
                score=round(float(item['score']), 6),
                citation=f'[S{index}]',
            )
            for index, item in enumerate(ordered, 1)
        ]

    @staticmethod
    async def answer(*, db: AsyncSession, user_id: int, is_admin: bool, obj: AnswerParam) -> GetAnswerDetail:
        started = time.perf_counter()
        trace_id = uuid.uuid4().hex
        effective_mode = (
            'agentic' if obj.mode == 'agentic' or (obj.mode == 'auto' and len(obj.question) > 80) else 'basic'
        )
        agent_state = {'retrieval_rounds': 1, 'tool_calls': 0, 'stop_reason': 'basic_retrieval'}
        if effective_mode == 'agentic':
            agent_state = agent_graph.invoke({
                'question': obj.question,
                'retrieval_rounds': 0,
                'tool_calls': 0,
                'stop_reason': '',
            })
        sources = await QueryService.retrieve(db=db, user_id=user_id, is_admin=is_admin, obj=obj)
        if not sources:
            result = GetAnswerDetail(
                answer='当前知识库中没有足够资料回答该问题。',
                sources=[],
                requested_mode=obj.mode,
                effective_mode=effective_mode,
                status='insufficient_evidence',
                retrieval_rounds=agent_state['retrieval_rounds'],
                stop_reason='no_sources',
                trace_id=trace_id,
            )
        else:
            context = '\n\n'.join(f'{source.citation} {source.content}' for source in sources)
            answer = await chat_provider.complete(question=obj.question, context=context)
            # Only server-issued citations are allowed in the response.
            known = {source.citation for source in sources}
            for token in set(part for part in answer.split() if part.startswith('[S') and part.endswith(']')) - known:
                answer = answer.replace(token, '')
            result = GetAnswerDetail(
                answer=answer,
                sources=sources,
                requested_mode=obj.mode,
                effective_mode=effective_mode,
                status='answered',
                retrieval_rounds=agent_state['retrieval_rounds'],
                stop_reason=agent_state['stop_reason'],
                trace_id=trace_id,
            )
        db.add(
            QueryLog(
                owner_id=user_id,
                knowledge_base_ids=obj.knowledge_base_ids,
                requested_mode=obj.mode,
                effective_mode=effective_mode,
                status=result.status,
                retrieval_rounds=result.retrieval_rounds,
                tool_calls=agent_state['tool_calls'],
                source_count=len(result.sources),
                latency_ms=int((time.perf_counter() - started) * 1000),
                trace_id=trace_id,
            )
        )
        return result


query_service = QueryService()
