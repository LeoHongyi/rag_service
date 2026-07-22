from backend.app.rag.chunking import clean_text, contextualize_chunk, split_parent_child_text, split_text
from backend.app.rag.lexical import (
    build_websearch_query,
    extract_exact_tokens,
    tokenize_search_text,
    weighted_rrf_scores,
)


def test_split_text_preserves_nonempty_content() -> None:
    chunks = split_text('甲' * 80 + '\n\n' + '乙' * 80, chunk_size=100, overlap=20)
    assert len(chunks) == 2
    assert chunks[0].startswith('甲')


def test_clean_text_removes_controls() -> None:
    assert clean_text('甲\x00\n\n\n乙') == '甲\n\n乙'


def test_contextualize_chunk_has_source_metadata() -> None:
    assert '文件：手册.md' in contextualize_chunk(filename='手册.md', heading_path=['安装'], content='正文')


def test_split_parent_child_text_keeps_heading_and_page_context() -> None:
    parents = split_parent_child_text(
        text='# 安装\n\n第一段内容。\n\n## 配置\n\n第二段内容。\n\n第 2 页\n\n第三段内容。',
        chunk_size=20,
        overlap=0,
    )

    assert [item.heading_path for item in parents] == [['安装'], ['安装', '配置'], ['第 2 页']]
    assert all(item.children for item in parents)
    assert '第二段' in parents[1].parent_content


def test_chinese_tokenizer_keeps_exact_identifier() -> None:
    tokens = tokenize_search_text('请查找 Qwen3-Embedding-0.6B 和订单号 SKU-2026-07。')

    assert 'Qwen3-Embedding-0.6B' in tokens
    assert 'SKU-2026-07' in tokens
    assert '查找' in tokens


def test_chinese_query_uses_bounded_or_terms_instead_of_all_term_and() -> None:
    query = build_websearch_query('知识检索最多支持多少个知识库？？？')

    assert ' OR ' in query
    assert '"知识库"' in query
    assert '？' not in query
    assert len(query.split(' OR ')) <= 16


def test_exact_tokens_are_normalized_without_splitting_identifiers() -> None:
    tokens = extract_exact_tokens('Qwen3-Rerank 与 TEXT-embedding-v4、api/v1、SKU_2026。')

    assert tokens == ['qwen3-rerank', 'text-embedding-v4', 'api/v1', 'sku_2026']


def test_weighted_rrf_protects_strong_dense_hit_from_lexical_noise() -> None:
    scores = weighted_rrf_scores(
        dense_ids=[1, 2, 3],
        lexical_ids=[4, 2, 3],
        rrf_k=60,
        dense_weight=1.0,
        lexical_weight=0.5,
    )

    assert scores[1] > scores[4]
    assert scores[2] > scores[1]
