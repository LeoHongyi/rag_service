import asyncio

from typing import Any, Self

import pytest

from backend.app.rag.adapters import embedding
from backend.common.exception import errors
from backend.core.conf import settings


class FakeResponse:
    @staticmethod
    def raise_for_status() -> None:
        return None

    @staticmethod
    def json() -> dict[str, list[dict[str, Any]]]:
        return {'data': [{'index': 0, 'embedding': [1.0, 0.0]}]}


class FakeAsyncClient:
    observed_timeout: float | None = None

    def __init__(self, *, timeout: float) -> None:
        self.observed_timeout = timeout
        FakeAsyncClient.observed_timeout = timeout

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> FakeResponse:
        return FakeResponse()


def test_embedding_provider_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_BASE_URL', 'http://127.0.0.1:9999/v1')
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_API_KEY', 'test-only')
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_DIMENSIONS', 2)
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_TIMEOUT_SECONDS', 0.25)
    monkeypatch.setattr(embedding.httpx, 'AsyncClient', FakeAsyncClient)

    vectors = asyncio.run(embedding.EmbeddingProvider().embed(['hello']))

    assert vectors == [[1.0, 0.0]]
    assert FakeAsyncClient.observed_timeout == pytest.approx(0.25)


def test_embedding_provider_falls_back_to_local_vectors_when_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_ALLOW_LOCAL_MODEL_FALLBACK', True)
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_BASE_URL', None)
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_API_KEY', None)
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_DIMENSIONS', 4)

    vectors = asyncio.run(embedding.EmbeddingProvider().embed(['hello']))

    assert len(vectors) == 1
    assert len(vectors[0]) == 4


def test_embedding_provider_warns_when_using_local_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """伪向量回退必须留下可审计痕迹，否则生产误配将完全静默。"""
    monkeypatch.setattr(settings, 'RAG_ALLOW_LOCAL_MODEL_FALLBACK', True)
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_BASE_URL', None)
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_API_KEY', None)
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_DIMENSIONS', 4)
    records: list[str] = []
    sink_id = embedding.log.add(lambda message: records.append(message.record['message']), level='WARNING')

    try:
        asyncio.run(embedding.EmbeddingProvider().embed(['hello']))
    finally:
        embedding.log.remove(sink_id)

    assert any('伪向量' in record for record in records)


def test_embedding_provider_fails_closed_when_fallback_disallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_ALLOW_LOCAL_MODEL_FALLBACK', False)
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_BASE_URL', None)
    monkeypatch.setattr(settings, 'RAG_EMBEDDING_API_KEY', 'test-only')

    with pytest.raises(errors.ServerError):
        asyncio.run(embedding.EmbeddingProvider().embed(['hello']))
