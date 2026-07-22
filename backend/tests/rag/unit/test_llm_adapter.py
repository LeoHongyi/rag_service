import asyncio

from typing import Any

import pytest

from typing_extensions import Self

from backend.app.rag.adapters import llm
from backend.core.conf import settings


class FakeResponse:
    @staticmethod
    def raise_for_status() -> None:
        return None

    @staticmethod
    def json() -> dict[str, Any]:
        return {
            'choices': [{'message': {'content': '回答 [S1]'}}],
            'usage': {'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15},
        }


class FakeAsyncClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> FakeResponse:
        return FakeResponse()


async def call_with_usage() -> tuple[str, llm.ChatUsage]:
    answer = await llm.ChatProvider().complete(question='问题', context='[S1] 资料')
    return answer, llm.get_chat_usage()


def test_chat_provider_records_actual_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_CHAT_BASE_URL', 'https://example.test/v1')
    monkeypatch.setattr(settings, 'RAG_CHAT_API_KEY', 'test-only')
    monkeypatch.setattr(llm.httpx, 'AsyncClient', FakeAsyncClient)

    answer, usage = asyncio.run(call_with_usage())

    assert answer == '回答 [S1]'
    assert usage == llm.ChatUsage(
        called=True,
        succeeded=True,
        prompt_tokens=12,
        completion_tokens=3,
        total_tokens=15,
    )
