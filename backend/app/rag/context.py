"""问答上下文选择、范围证据与引用校验。"""

import re

from dataclasses import dataclass

from backend.app.rag.schema.query import GetSourceDetail

_CITATION_PATTERN = re.compile(r'\[S\d+\]')
_SCOPE_MARKERS = ('本项目', '本系统', '本服务', '本知识库', '我们的')


@dataclass(frozen=True)
class ContextSelection:
    """受来源数量与近似 Token 预算约束的上下文。"""

    context: str
    sources: list[GetSourceDetail]


def estimate_token_units(text: str) -> int:
    """以四分之一 Token 为单位保守估算中英文混合文本。"""
    return sum(4 if '\u3400' <= character <= '\u9fff' else 1 for character in text)


def _truncate_to_units(text: str, *, available_units: int) -> str:
    used = 0
    characters: list[str] = []
    for character in text:
        cost = 4 if '\u3400' <= character <= '\u9fff' else 1
        if used + cost > available_units:
            break
        characters.append(character)
        used += cost
    return ''.join(characters).rstrip()


def build_bounded_context(*, sources: list[GetSourceDetail], max_sources: int, max_tokens: int) -> ContextSelection:
    """去重来源并构造有界上下文；中文按一字一 Token 保守预算。"""
    if max_sources < 1 or max_tokens < 1:
        raise ValueError('上下文来源数和 Token 预算必须大于 0')
    max_units = max_tokens * 4
    used_units = 0
    selected_sources: list[GetSourceDetail] = []
    parts: list[str] = []
    seen: set[tuple[int, str]] = set()
    for source in sources:
        dedupe_key = (source.document_id, source.content)
        if dedupe_key in seen or len(selected_sources) == max_sources:
            continue
        prefix = f'{source.citation} '
        available = max_units - used_units - estimate_token_units(prefix)
        if available <= 0:
            break
        content = _truncate_to_units(source.content, available_units=available)
        if not content:
            break
        part = prefix + content
        parts.append(part)
        selected_sources.append(source.model_copy(update={'content': content}))
        seen.add(dedupe_key)
        used_units += estimate_token_units(part)
        if used_units >= max_units:
            break
    return ContextSelection(context='\n\n'.join(parts), sources=selected_sources)


def has_sufficient_scope_evidence(*, question: str, sources: list[GetSourceDetail]) -> bool:
    """对明确指向当前系统的查询执行保守、确定性的范围一致性检查。"""
    required = [marker for marker in _SCOPE_MARKERS if marker in question]
    if not required:
        return bool(sources)
    return any(marker in source.content for marker in required for source in sources)


def sanitize_answer_citations(*, answer: str, sources: list[GetSourceDetail]) -> str:
    """移除模型生成但未由服务端签发的引用标识。"""
    known = {source.citation for source in sources}
    return _CITATION_PATTERN.sub(lambda match: match.group(0) if match.group(0) in known else '', answer)


def extract_cited_chunk_ids(*, answer: str, sources: list[GetSourceDetail]) -> list[int]:
    """按答案首次出现顺序返回实际使用的已知引用 Chunk ID。"""
    by_citation = {source.citation: source.chunk_id for source in sources}
    return list(
        dict.fromkeys(
            by_citation[citation] for citation in _CITATION_PATTERN.findall(answer) if citation in by_citation
        )
    )
