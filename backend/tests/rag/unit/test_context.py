from backend.app.rag.context import (
    build_bounded_context,
    extract_cited_chunk_ids,
    has_sufficient_scope_evidence,
    sanitize_answer_citations,
)
from backend.app.rag.schema.query import GetSourceDetail


def source(*, chunk_id: int, citation: str, content: str, document_id: int = 1) -> GetSourceDetail:
    return GetSourceDetail(
        knowledge_base_id=1,
        document_id=document_id,
        document_name='资料.md',
        chunk_id=chunk_id,
        chunk_index=chunk_id,
        content=content,
        score=1.0,
        citation=citation,
    )


def test_context_deduplicates_parent_content_and_respects_source_limit() -> None:
    sources = [
        source(chunk_id=1, citation='[S1]', content='同一父节'),
        source(chunk_id=2, citation='[S2]', content='同一父节'),
        source(chunk_id=3, citation='[S3]', content='另一父节'),
    ]

    selection = build_bounded_context(sources=sources, max_sources=2, max_tokens=100)

    assert [item.chunk_id for item in selection.sources] == [1, 3]
    assert selection.context.count('同一父节') == 1


def test_context_truncates_at_conservative_chinese_token_budget() -> None:
    selection = build_bounded_context(
        sources=[source(chunk_id=1, citation='[S1]', content='中文内容' * 20)],
        max_sources=1,
        max_tokens=8,
    )

    assert selection.sources
    assert len(selection.sources[0].content) < 80


def test_scope_evidence_requires_matching_current_project_marker() -> None:
    external = [source(chunk_id=1, citation='[S1]', content='阿里云知识库管理员权限。')]
    internal = [source(chunk_id=2, citation='[S2]', content='本项目使用所有者校验。')]

    assert not has_sufficient_scope_evidence(question='本项目如何实现权限？', sources=external)
    assert has_sufficient_scope_evidence(question='本项目如何实现权限？', sources=internal)
    assert has_sufficient_scope_evidence(question='阿里云如何实现权限？', sources=external)


def test_citations_keep_only_known_tokens_and_report_actual_usage() -> None:
    sources = [
        source(chunk_id=11, citation='[S1]', content='甲'),
        source(chunk_id=22, citation='[S2]', content='乙'),
    ]

    answer = sanitize_answer_citations(answer='结论[S2]，未知[S9]，重复[S2]。', sources=sources)

    assert '[S9]' not in answer
    assert extract_cited_chunk_ids(answer=answer, sources=sources) == [22]
