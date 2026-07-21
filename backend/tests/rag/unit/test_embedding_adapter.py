import asyncio

from typing import Any

import pytest

from typing_extensions import Self

from backend.app.rag.adapters import embedding
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
