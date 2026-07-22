import time
import uuid

from typing import TypedDict

import httpx

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rag.adapters.embedding import embedding_provider
from backend.app.rag.adapters.llm import chat_provider, reset_chat_usage
from backend.app.rag.adapters.rerank import rerank_provider
from backend.app.rag.agent.graph import agent_graph
from backend.app.rag.context import build_bounded_context, has_sufficient_scope_evidence, sanitize_answer_citations
from backend.app.rag.enums import DocumentStatus
from backend.app.rag.lexical import build_websearch_query, extract_exact_tokens, weighted_rrf_scores
from backend.app.rag.model import Chunk, Document, KnowledgeBase, QueryLog
from backend.app.rag.schema.query import AnswerParam, GetAnswerDetail, GetSourceDetail, RetrieveParam
from backend.common.exception import errors
from backend.core.conf import settings


class _MergedResult(TypedDict):
    chunk: Chunk
    name: str
    score: float
    dense: float
    rerank: float | None


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
    def _select_context_results(*, ordered: list[_MergedResult], top_k: int) -> list[_MergedResult]:
        if not settings.RAG_PARENT_CONTEXT_ENABLED:
            return ordered[:top_k]
        unique_ordered: list[_MergedResult] = []
        seen_contexts: set[int] = set()
        for item in ordered:
            context_id = item['chunk'].parent_chunk_id or item['chunk'].id
            if context_id in seen_contexts:
                continue
            unique_ordered.append(item)
            seen_contexts.add(context_id)
            if len(unique_ordered) == top_k:
                break
        return unique_ordered

    @staticmethod
    async def _get_parent_content(*, db: AsyncSession, ordered: list[_MergedResult]) -> dict[int, str]:
        if not settings.RAG_PARENT_CONTEXT_ENABLED:
            return {}
        parent_ids = {item['chunk'].parent_chunk_id for item in ordered if item['chunk'].parent_chunk_id is not None}
        if not parent_ids:
            return {}
        parents = await db.execute(
            select(Chunk.id, Chunk.content).where(Chunk.id.in_(parent_ids), Chunk.is_parent, Chunk.deleted == 0)
        )
        return dict(parents.all())

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
                Chunk.is_parent.is_(False),
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
        tsquery = func.websearch_to_tsquery('simple', build_websearch_query(obj.question))
        text_match = func.to_tsvector('simple', Chunk.search_text).op('@@')(tsquery)
        exact_tokens = extract_exact_tokens(obj.question)
        lexical_condition = text_match
        exact_rank = 0.0
        if exact_tokens:
            exact_match = Chunk.exact_tokens.overlap(exact_tokens)
            lexical_condition = or_(text_match, exact_match)
            exact_rank = case((exact_match, 10.0), else_=0.0)
        lexical_rank = (func.ts_rank_cd(func.to_tsvector('simple', Chunk.search_text), tsquery) + exact_rank).label(
            'lexical_rank'
        )
        lexical_rows = (
            await db.execute(
                base
                .add_columns(lexical_rank)
                .where(lexical_condition)
                .order_by(lexical_rank.desc())
                .limit(settings.RAG_LEXICAL_CANDIDATE_K)
            )
        ).all()

        merged: dict[int, _MergedResult] = {}
        for chunk, name, value in dense_rows:
            merged[chunk.id] = {
                'chunk': chunk,
                'name': name,
                'score': 0.0,
                'dense': max(0.0, 1 - float(value)),
                'rerank': None,
            }
        for chunk, name, _value in lexical_rows:
            merged.setdefault(
                chunk.id,
                {'chunk': chunk, 'name': name, 'score': 0.0, 'dense': 0.0, 'rerank': None},
            )
        scores = weighted_rrf_scores(
            dense_ids=[row[0].id for row in dense_rows],
            lexical_ids=[row[0].id for row in lexical_rows],
            rrf_k=settings.RAG_RRF_K,
            dense_weight=settings.RAG_DENSE_RRF_WEIGHT,
            lexical_weight=settings.RAG_LEXICAL_RRF_WEIGHT,
        )
        for chunk_id, score in scores.items():
            merged[chunk_id]['score'] = score

        ordered = sorted(merged.values(), key=lambda item: float(item['score']), reverse=True)
        try:
            reranked = await rerank_provider.rerank(
                query=obj.question, documents=[item['chunk'].contextual_content for item in ordered]
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            reranked = []
        if reranked:
            by_index = {item.index: item.score for item in reranked}
            for index, item in enumerate(ordered):
                item['rerank'] = by_index.get(index)
            ordered.sort(
                key=lambda item: float(item['rerank']) if item['rerank'] is not None else float('-inf'),
                reverse=True,
            )
        ordered = QueryService._select_context_results(ordered=ordered, top_k=obj.top_k)
        parent_content = await QueryService._get_parent_content(db=db, ordered=ordered)
        return [
            GetSourceDetail(
                knowledge_base_id=item['chunk'].knowledge_base_id,
                document_id=item['chunk'].document_id,
                document_name=str(item['name']),
                chunk_id=item['chunk'].id,
                chunk_index=item['chunk'].chunk_index,
                content=parent_content.get(item['chunk'].parent_chunk_id, item['chunk'].content),
                score=round(float(item['score']), 6),
                rerank_score=item['rerank'],
                citation=f'[S{index}]',
            )
            for index, item in enumerate(ordered, 1)
        ]

    @staticmethod
    async def answer(*, db: AsyncSession, user_id: int, is_admin: bool, obj: AnswerParam) -> GetAnswerDetail:
        reset_chat_usage()
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
        if not has_sufficient_scope_evidence(question=obj.question, sources=sources):
            result = GetAnswerDetail(
                answer='当前知识库中没有足够资料回答该问题。',
                sources=[],
                requested_mode=obj.mode,
                effective_mode=effective_mode,
                status='insufficient_evidence',
                retrieval_rounds=agent_state['retrieval_rounds'],
                stop_reason='insufficient_scope_evidence' if sources else 'no_sources',
                trace_id=trace_id,
            )
        else:
            selection = build_bounded_context(
                sources=sources,
                max_sources=settings.RAG_FINAL_CONTEXT_K,
                max_tokens=settings.RAG_CONTEXT_MAX_TOKENS,
            )
            answer = await chat_provider.complete(question=obj.question, context=selection.context)
            answer = sanitize_answer_citations(answer=answer, sources=selection.sources)
            result = GetAnswerDetail(
                answer=answer,
                sources=selection.sources,
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
