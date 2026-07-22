"""确定性中文词法检索辅助函数。"""

import re

from collections.abc import Sequence

import jieba  # type: ignore[import-untyped]

_EXACT_TOKEN_PATTERN = re.compile(r'[A-Za-z0-9]+(?:[._:/-][A-Za-z0-9]+)+|[A-Za-z0-9]+')
_MAX_QUERY_TERMS = 16


def tokenize_search_text(text: str) -> str:
    """在索引与查询两端使用同一版本 jieba，并保留产品编号等精确 Token。"""
    tokens = [token.strip() for token in jieba.lcut(text, HMM=False) if token.strip()]
    tokens.extend(match.group(0) for match in _EXACT_TOKEN_PATTERN.finditer(text))
    return ' '.join(tokens)


def extract_exact_tokens(text: str) -> list[str]:
    """提取可使用 GIN 数组索引精确匹配的规范化 ASCII 标识符。"""
    return list(dict.fromkeys(match.group(0).casefold() for match in _EXACT_TOKEN_PATTERN.finditer(text)))


def build_websearch_query(text: str) -> str:
    """生成去标点、受长度限制的 OR 查询，避免所有 Token 的 AND 条件清空候选。"""
    terms: list[str] = []
    tokens = [*extract_exact_tokens(text), *tokenize_search_text(text).split()]
    normalized_terms: set[str] = set()
    for token in tokens:
        safe_token = token.replace('"', '').strip()
        normalized = safe_token.casefold()
        if not any(character.isalnum() for character in safe_token):
            continue
        if len(safe_token) == 1 and '\u4e00' <= safe_token <= '\u9fff':
            continue
        if not safe_token or normalized in normalized_terms:
            continue
        terms.append(safe_token)
        normalized_terms.add(normalized)
        if len(terms) == _MAX_QUERY_TERMS:
            break
    return ' OR '.join(f'"{term}"' for term in terms)


def weighted_rrf_scores(
    *,
    dense_ids: Sequence[int],
    lexical_ids: Sequence[int],
    rrf_k: int,
    dense_weight: float,
    lexical_weight: float,
) -> dict[int, float]:
    """按两个独立排名计算带权 RRF，避免通用词候选压过强稠密命中。"""
    scores: dict[int, float] = {}
    for rank, chunk_id in enumerate(dense_ids, 1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + dense_weight / (rrf_k + rank)
    for rank, chunk_id in enumerate(lexical_ids, 1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + lexical_weight / (rrf_k + rank)
    return scores
