"""可降级的 OpenAI 兼容与 DashScope Rerank 适配器。"""

from contextvars import ContextVar
from dataclasses import dataclass

import httpx

from backend.core.conf import settings


@dataclass(frozen=True)
class RerankResult:
    """供应商无关的重排结果。"""

    index: int
    score: float


@dataclass(frozen=True)
class RerankUsage:
    """一次当前异步上下文内的 Rerank 调用用量。"""

    called: bool = False
    succeeded: bool = False
    total_tokens: int = 0


_rerank_usage: ContextVar[RerankUsage | None] = ContextVar('rag_rerank_usage', default=None)


def get_rerank_usage() -> RerankUsage:
    """返回当前异步上下文最近一次 Rerank 调用的用量。"""
    return _rerank_usage.get() or RerankUsage()


class RerankProvider:
    """仅在完整配置且显式启用时调用远端重排服务。"""

    async def rerank(self, *, query: str, documents: list[str]) -> list[RerankResult]:
        _rerank_usage.set(RerankUsage())
        if not settings.RAG_RERANK_ENABLED:
            return []
        if not all((settings.RAG_RERANK_BASE_URL, settings.RAG_RERANK_API_KEY, settings.RAG_RERANK_MODEL)):
            raise ValueError('Rerank 已启用但配置不完整')
        base_url = settings.RAG_RERANK_BASE_URL.rstrip('/')
        top_n = min(len(documents), settings.RAG_RERANK_TOP_N)
        if settings.RAG_RERANK_PROTOCOL == 'dashscope':
            endpoint = (
                base_url
                if base_url.endswith('/services/rerank/text-rerank/text-rerank')
                else f'{base_url}/services/rerank/text-rerank/text-rerank'
            )
            payload = {
                'model': settings.RAG_RERANK_MODEL,
                'input': {'query': query, 'documents': documents},
                'parameters': {'top_n': top_n},
            }
        else:
            endpoint = base_url if base_url.endswith('/reranks') else f'{base_url}/reranks'
            payload = {
                'model': settings.RAG_RERANK_MODEL,
                'query': query,
                'documents': documents,
                'top_n': top_n,
            }
        headers = {'Authorization': f'Bearer {settings.RAG_RERANK_API_KEY}'}
        _rerank_usage.set(RerankUsage(called=True))
        async with httpx.AsyncClient(timeout=settings.RAG_RERANK_TIMEOUT_SECONDS) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
        body = response.json()
        results = (
            body.get('output', {}).get('results', [])
            if settings.RAG_RERANK_PROTOCOL == 'dashscope'
            else body.get('results', body.get('data', []))
        )
        parsed = [
            RerankResult(index=int(item['index']), score=float(item.get('relevance_score', item.get('score'))))
            for item in results
        ]
        if any(item.index < 0 or item.index >= len(documents) for item in parsed):
            raise ValueError('Rerank 返回了无效候选索引')
        total_tokens = int(body.get('usage', {}).get('total_tokens', 0))
        _rerank_usage.set(RerankUsage(called=True, succeeded=True, total_tokens=total_tokens))
        return parsed


rerank_provider = RerankProvider()
