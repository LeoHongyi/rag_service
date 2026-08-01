"""Outbox 投递失败处理策略的回归测试。

覆盖两件事：失败摘要必须脱敏（Broker URL 内嵌凭据），以及失败次数达到上限
后必须转入 DEAD——否则永远不会成功的事件会持续挤占固定大小的认领批次。
"""

from types import SimpleNamespace

import httpx
import pytest

from backend.app.rag.enums import OutboxStatus
from backend.app.rag.indexing import is_retryable_index_error, sanitize_dispatch_error
from backend.app.rag.service.outbox_service import mark_failed


def _event() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        event_type='rag.document.index.requested',
        status=OutboxStatus.PENDING,
        dispatch_attempts=0,
        last_error=None,
    )


def test_failed_event_stays_retryable_below_the_cap() -> None:
    event = _event()

    mark_failed(event=event, exc=ConnectionError('boom'), max_attempts=3)

    assert event.status == OutboxStatus.FAILED
    assert event.dispatch_attempts == 1


def test_failed_event_becomes_dead_at_the_cap() -> None:
    event = _event()
    event.dispatch_attempts = 2

    mark_failed(event=event, exc=ConnectionError('boom'), max_attempts=3)

    assert event.status == OutboxStatus.DEAD
    assert event.dispatch_attempts == 3


def test_dispatch_error_summary_never_leaks_the_broker_url() -> None:
    """Broker URL 形如 amqp://user:password@host，绝不能进入 last_error。"""
    leaky = ConnectionError('Error connecting to amqp://guest:s3cr3t@10.0.0.5:5672//: timed out')
    event = _event()

    mark_failed(event=event, exc=leaky, max_attempts=10)

    assert 's3cr3t' not in event.last_error
    assert '10.0.0.5' not in event.last_error
    assert 'amqp://' not in event.last_error
    assert event.last_error == '任务投递失败：消息中间件连接异常'


def test_unknown_event_type_summary_is_also_redacted() -> None:
    assert sanitize_dispatch_error(ValueError('不支持的 Outbox 事件类型: x')) == '任务投递失败：事件类型或载荷不受支持'


@pytest.mark.parametrize('status_code', [401, 403])
def test_auth_failures_are_retryable(status_code: int) -> None:
    """密钥过期/轮换是环境问题，对所有文档同时生效，不应逐个判为永久失败。"""
    exc = httpx.HTTPStatusError(
        'auth',
        request=httpx.Request('POST', 'https://example.test/v1/embeddings'),
        response=httpx.Response(status_code),
    )

    assert is_retryable_index_error(exc) is True


@pytest.mark.parametrize('status_code', [400, 404, 422])
def test_client_errors_remain_permanent(status_code: int) -> None:
    exc = httpx.HTTPStatusError(
        'bad',
        request=httpx.Request('POST', 'https://example.test/v1/embeddings'),
        response=httpx.Response(status_code),
    )

    assert is_retryable_index_error(exc) is False
