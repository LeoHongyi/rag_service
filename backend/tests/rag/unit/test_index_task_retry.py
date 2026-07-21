import asyncio

from typing import Any

import httpx
import pytest

from backend.app.rag.enums import DocumentStatus
from backend.app.task.tasks.rag import tasks
from backend.core.conf import settings


class Transaction:
    async def __aenter__(self) -> object:
        await asyncio.sleep(0)
        return object()

    async def __aexit__(self, *_args: object) -> None:
        await asyncio.sleep(0)


class DatabaseSessions:
    @staticmethod
    def begin() -> Transaction:
        return Transaction()


class RetryRequestedError(Exception):
    pass


def test_index_task_uses_late_ack_and_finite_retries() -> None:
    assert tasks.index_document.max_retries == settings.RAG_INDEX_MAX_RETRIES
    assert tasks.index_document.acks_late is True
    assert tasks.index_document.reject_on_worker_lost is True
    assert tasks.index_document.autoretry_for == ()


def test_temporary_index_failure_is_marked_pending_and_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    marked: list[dict[str, Any]] = []
    retried: list[tuple[Exception, int]] = []

    async def fake_claim(**_kwargs: Any) -> tuple[str, int]:
        await asyncio.sleep(0)
        return 'claimed', 3

    async def fail_index(**_kwargs: Any) -> str:
        await asyncio.sleep(0)
        raise httpx.ReadTimeout('provider timed out')

    async def fake_mark(**kwargs: Any) -> bool:
        await asyncio.sleep(0)
        marked.append(kwargs)
        return True

    def fake_retry(*, exc: Exception, countdown: int) -> None:
        retried.append((exc, countdown))
        raise RetryRequestedError

    monkeypatch.setattr(tasks, 'async_db_session', DatabaseSessions())
    monkeypatch.setattr(tasks.document_service, 'claim_index', fake_claim)
    monkeypatch.setattr(tasks.document_service, 'index_claimed_document', fail_index)
    monkeypatch.setattr(tasks.document_service, 'mark_index_failure', fake_mark)
    monkeypatch.setattr(tasks.index_document, 'retry', fake_retry)

    tasks.index_document.push_request(retries=0)
    try:
        with pytest.raises(RetryRequestedError):
            asyncio.run(tasks.index_document.run(7, 3))
    finally:
        tasks.index_document.pop_request()

    assert marked[0]['status'] == DocumentStatus.PENDING
    assert marked[0]['error_message'] == '模型服务请求超时'
    assert isinstance(retried[0][0], httpx.ReadTimeout)
    assert retried[0][1] == 1


def test_permanent_index_failure_is_marked_failed_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    marked: list[dict[str, Any]] = []

    async def fake_claim(**_kwargs: Any) -> tuple[str, int]:
        await asyncio.sleep(0)
        return 'claimed', 3

    async def fail_index(**_kwargs: Any) -> str:
        await asyncio.sleep(0)
        raise ValueError('PDF 文件损坏')

    async def fake_mark(**kwargs: Any) -> bool:
        await asyncio.sleep(0)
        marked.append(kwargs)
        return True

    def unexpected_retry(**_kwargs: Any) -> None:
        raise AssertionError('永久错误不应重试')

    monkeypatch.setattr(tasks, 'async_db_session', DatabaseSessions())
    monkeypatch.setattr(tasks.document_service, 'claim_index', fake_claim)
    monkeypatch.setattr(tasks.document_service, 'index_claimed_document', fail_index)
    monkeypatch.setattr(tasks.document_service, 'mark_index_failure', fake_mark)
    monkeypatch.setattr(tasks.index_document, 'retry', unexpected_retry)

    tasks.index_document.push_request(retries=0)
    try:
        result = asyncio.run(tasks.index_document.run(7, 3))
    finally:
        tasks.index_document.pop_request()

    assert result == DocumentStatus.FAILED.value
    assert marked[0]['status'] == DocumentStatus.FAILED
    assert marked[0]['error_message'] == 'PDF 文件损坏'


def test_exhausted_temporary_failure_is_marked_failed_without_another_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marked: list[dict[str, Any]] = []

    async def fake_claim(**_kwargs: Any) -> tuple[str, int]:
        await asyncio.sleep(0)
        return 'claimed', 3

    async def fail_index(**_kwargs: Any) -> str:
        await asyncio.sleep(0)
        raise httpx.ReadTimeout('provider timed out')

    async def fake_mark(**kwargs: Any) -> bool:
        await asyncio.sleep(0)
        marked.append(kwargs)
        return True

    def unexpected_retry(**_kwargs: Any) -> None:
        raise AssertionError('重试耗尽后不应再次重试')

    monkeypatch.setattr(tasks, 'async_db_session', DatabaseSessions())
    monkeypatch.setattr(tasks.document_service, 'claim_index', fake_claim)
    monkeypatch.setattr(tasks.document_service, 'index_claimed_document', fail_index)
    monkeypatch.setattr(tasks.document_service, 'mark_index_failure', fake_mark)
    monkeypatch.setattr(tasks.index_document, 'retry', unexpected_retry)

    tasks.index_document.push_request(retries=settings.RAG_INDEX_MAX_RETRIES)
    try:
        with pytest.raises(httpx.ReadTimeout):
            asyncio.run(tasks.index_document.run(7, 3))
    finally:
        tasks.index_document.pop_request()

    assert marked[0]['status'] == DocumentStatus.FAILED
    assert marked[0]['error_message'] == '模型服务请求超时'
