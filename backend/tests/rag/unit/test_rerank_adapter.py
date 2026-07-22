import asyncio

from typing import Any

import pytest

from typing_extensions import Self

from backend.app.rag.adapters import rerank
from backend.core.conf import settings


class FakeResponse:
    body: dict[str, Any] = {}

    @staticmethod
    def raise_for_status() -> None:
        return None

    @classmethod
    def json(cls) -> dict[str, Any]:
        return cls.body


class FakeAsyncClient:
    observed_url = ''
    observed_payload: dict[str, Any] = {}

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> FakeResponse:
        del headers
        FakeAsyncClient.observed_url = url
        FakeAsyncClient.observed_payload = json
        return FakeResponse()


def configure_provider(monkeypatch: pytest.MonkeyPatch, *, protocol: str) -> None:
    monkeypatch.setattr(settings, 'RAG_RERANK_ENABLED', True)
    monkeypatch.setattr(settings, 'RAG_RERANK_PROTOCOL', protocol)
    monkeypatch.setattr(settings, 'RAG_RERANK_BASE_URL', 'https://example.test/api/v1')
    monkeypatch.setattr(settings, 'RAG_RERANK_API_KEY', 'test-only')
    monkeypatch.setattr(settings, 'RAG_RERANK_MODEL', 'qwen3-rerank')
    monkeypatch.setattr(rerank.httpx, 'AsyncClient', FakeAsyncClient)


async def run_with_usage(*, query: str, documents: list[str]) -> tuple[list[rerank.RerankResult], rerank.RerankUsage]:
    results = await rerank.RerankProvider().rerank(query=query, documents=documents)
    return results, rerank.get_rerank_usage()


def test_rerank_is_disabled_without_remote_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_RERANK_ENABLED', False)

    assert asyncio.run(rerank.RerankProvider().rerank(query='问题', documents=['资料'])) == []


def test_rerank_requires_complete_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_RERANK_ENABLED', True)
    monkeypatch.setattr(settings, 'RAG_RERANK_BASE_URL', None)
    monkeypatch.setattr(settings, 'RAG_RERANK_API_KEY', None)
    monkeypatch.setattr(settings, 'RAG_RERANK_MODEL', None)

    with pytest.raises(ValueError, match='配置不完整'):
        asyncio.run(rerank.RerankProvider().rerank(query='问题', documents=['资料']))


def test_openai_rerank_parses_results_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_provider(monkeypatch, protocol='openai')
    FakeResponse.body = {
        'results': [{'index': 1, 'relevance_score': 0.9}],
        'usage': {'total_tokens': 12},
    }

    results, usage = asyncio.run(run_with_usage(query='问题', documents=['甲', '乙']))

    assert results == [rerank.RerankResult(index=1, score=0.9)]
    assert FakeAsyncClient.observed_url == 'https://example.test/api/v1/reranks'
    assert FakeAsyncClient.observed_payload['query'] == '问题'
    assert usage == rerank.RerankUsage(called=True, succeeded=True, total_tokens=12)


def test_dashscope_rerank_uses_nested_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_provider(monkeypatch, protocol='dashscope')
    FakeResponse.body = {
        'output': {'results': [{'index': 0, 'relevance_score': 0.8}]},
        'usage': {'total_tokens': 18},
    }

    results, usage = asyncio.run(run_with_usage(query='问题', documents=['甲', '乙']))

    assert results == [rerank.RerankResult(index=0, score=0.8)]
    assert FakeAsyncClient.observed_url.endswith('/services/rerank/text-rerank/text-rerank')
    assert FakeAsyncClient.observed_payload['input'] == {'query': '问题', 'documents': ['甲', '乙']}
    assert FakeAsyncClient.observed_payload['parameters'] == {'top_n': 2}
    assert usage.total_tokens == 18


def test_rerank_rejects_out_of_range_index(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_provider(monkeypatch, protocol='openai')
    FakeResponse.body = {'results': [{'index': 2, 'relevance_score': 0.9}]}

    async def call_invalid() -> rerank.RerankUsage:
        with pytest.raises(ValueError, match='无效候选索引'):
            await rerank.RerankProvider().rerank(query='问题', documents=['甲', '乙'])
        return rerank.get_rerank_usage()

    assert asyncio.run(call_invalid()) == rerank.RerankUsage(called=True)
