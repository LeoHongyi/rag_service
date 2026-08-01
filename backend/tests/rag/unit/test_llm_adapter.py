import asyncio

from typing import Any, Self

import pytest

from backend.app.rag.adapters import llm
from backend.common.exception import errors
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
    observed_timeout: float | None = None

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout
        FakeAsyncClient.observed_timeout = timeout

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, *_args: object, **_kwargs: object) -> FakeResponse:
        return FakeResponse()


def _fake_client_returning(body: dict[str, Any]) -> type:
    """构造一个返回指定响应体的 httpx.AsyncClient 替身。"""

    class _Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, Any]:
            return body

    class _Client(FakeAsyncClient):
        async def post(self, *_args: object, **_kwargs: object) -> _Response:
            return _Response()

    return _Client


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


def test_chat_provider_returns_placeholder_when_fallback_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_ALLOW_LOCAL_MODEL_FALLBACK', True)
    monkeypatch.setattr(settings, 'RAG_CHAT_BASE_URL', None)
    monkeypatch.setattr(settings, 'RAG_CHAT_API_KEY', None)

    answer = asyncio.run(llm.ChatProvider().complete(question='问题', context='[S1] 资料'))

    assert answer.startswith('未配置聊天模型')


def test_chat_provider_fails_closed_when_fallback_disallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_ALLOW_LOCAL_MODEL_FALLBACK', False)
    monkeypatch.setattr(settings, 'RAG_CHAT_BASE_URL', None)
    monkeypatch.setattr(settings, 'RAG_CHAT_API_KEY', None)

    with pytest.raises(errors.ServerError):
        asyncio.run(llm.ChatProvider().complete(question='问题', context='[S1] 资料'))


def _configure_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'RAG_CHAT_BASE_URL', 'https://example.test/v1')
    monkeypatch.setattr(settings, 'RAG_CHAT_API_KEY', 'test-only')


def test_chat_provider_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """超时必须来自配置，不能硬编码，否则运维无法为慢供应商调参。"""
    _configure_chat(monkeypatch)
    monkeypatch.setattr(settings, 'RAG_CHAT_TIMEOUT_SECONDS', 7.5)
    monkeypatch.setattr(llm.httpx, 'AsyncClient', FakeAsyncClient)

    asyncio.run(llm.ChatProvider().complete(question='问题', context='[S1] 资料'))

    assert FakeAsyncClient.observed_timeout == pytest.approx(7.5)


def test_chat_provider_rejects_response_without_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    """内容安全拦截等场景会返回 choices 为空的合法响应，不得抛 IndexError。"""
    _configure_chat(monkeypatch)
    monkeypatch.setattr(llm.httpx, 'AsyncClient', _fake_client_returning({'choices': [], 'usage': {}}))

    with pytest.raises(errors.ServerError):
        asyncio.run(llm.ChatProvider().complete(question='问题', context='[S1] 资料'))


def test_chat_provider_rejects_null_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """拒答或工具调用时 content 可能为 null，不得抛 AttributeError。"""
    _configure_chat(monkeypatch)
    monkeypatch.setattr(
        llm.httpx, 'AsyncClient', _fake_client_returning({'choices': [{'message': {'content': None}}], 'usage': {}})
    )

    with pytest.raises(errors.ServerError):
        asyncio.run(llm.ChatProvider().complete(question='问题', context='[S1] 资料'))
