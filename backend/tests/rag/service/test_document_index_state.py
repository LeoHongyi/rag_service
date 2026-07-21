import asyncio

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.rag.enums import DocumentStatus
from backend.app.rag.service.document_service import DocumentService
from backend.utils.timezone import timezone


def test_index_content_propagates_failure_to_task_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    document = SimpleNamespace(filename='broken.pdf', status=DocumentStatus.PENDING)

    def fail_parse(**_kwargs: Any) -> str:
        raise ValueError('PDF 文件损坏')

    monkeypatch.setattr('backend.app.rag.parsers.text.parse_document', fail_parse)

    with pytest.raises(ValueError, match='PDF 文件损坏'):
        asyncio.run(DocumentService.index_content(db=object(), document=document, content=b'%PDF-broken'))

    assert document.status == DocumentStatus.PROCESSING


def test_pending_current_version_is_claimed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    document = SimpleNamespace(id=7, index_version=3, status=DocumentStatus.PENDING, error_message='old error')

    async def fake_get_for_update(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        return document

    monkeypatch.setattr(
        'backend.app.rag.service.document_service.document_dao.get_live_for_update',
        fake_get_for_update,
    )

    result, claimed_version = asyncio.run(DocumentService.claim_index(db=object(), document_id=7, index_version=3))

    assert result == 'claimed'
    assert claimed_version == 3
    assert document.status == DocumentStatus.PROCESSING
    assert document.error_message is None


@pytest.mark.parametrize(
    ('status', 'index_version', 'expected'),
    [
        (DocumentStatus.PROCESSING, 3, 'already_processing'),
        (DocumentStatus.READY, 3, 'already_ready'),
        (DocumentStatus.DELETING, 3, 'delete_requested'),
        (DocumentStatus.FAILED, 3, 'index_failed'),
        (DocumentStatus.PENDING, 4, 'stale_index_request'),
    ],
)
def test_non_claimable_document_is_not_changed(
    monkeypatch: pytest.MonkeyPatch,
    status: DocumentStatus,
    index_version: int,
    expected: str,
) -> None:
    document = SimpleNamespace(id=7, index_version=index_version, status=status, error_message='existing')

    async def fake_get_for_update(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        return document

    monkeypatch.setattr(
        'backend.app.rag.service.document_service.document_dao.get_live_for_update',
        fake_get_for_update,
    )

    result, claimed_version = asyncio.run(DocumentService.claim_index(db=object(), document_id=7, index_version=3))

    assert result == expected
    assert claimed_version == index_version
    assert document.status == status
    assert document.error_message == 'existing'


def test_stale_pending_and_processing_documents_are_recovered(monkeypatch: pytest.MonkeyPatch) -> None:
    stale_time = timezone.now() - timedelta(minutes=30)
    documents = [
        SimpleNamespace(
            id=7,
            index_version=2,
            status=DocumentStatus.PENDING,
            error_message=None,
            updated_time=stale_time,
        ),
        SimpleNamespace(
            id=8,
            index_version=5,
            status=DocumentStatus.PROCESSING,
            error_message=None,
            updated_time=stale_time,
        ),
    ]

    async def fake_get_stale(*_args: Any, **_kwargs: Any) -> list[SimpleNamespace]:
        await asyncio.sleep(0)
        return documents

    monkeypatch.setattr(
        'backend.app.rag.service.document_service.document_dao.get_stale_index_documents',
        fake_get_stale,
    )

    recovered = asyncio.run(
        DocumentService.recover_stale_indexes(
            db=object(),
            stale_before=timezone.now() - timedelta(minutes=15),
            limit=100,
        )
    )

    assert recovered == [(7, 2), (8, 5)]
    assert [document.status for document in documents] == [DocumentStatus.PENDING, DocumentStatus.PENDING]
    assert all(document.error_message == '索引任务超时，已重新排队' for document in documents)
    assert all(document.updated_time > stale_time for document in documents)


@pytest.mark.parametrize(
    ('status', 'index_version'),
    [
        (DocumentStatus.READY, 3),
        (DocumentStatus.DELETING, 3),
        (DocumentStatus.PROCESSING, 4),
    ],
)
def test_failure_update_does_not_overwrite_terminal_or_newer_version(
    monkeypatch: pytest.MonkeyPatch,
    status: DocumentStatus,
    index_version: int,
) -> None:
    document = SimpleNamespace(
        id=7,
        index_version=index_version,
        status=status,
        error_message='existing',
    )

    async def fake_get_for_update(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        return document

    monkeypatch.setattr(
        'backend.app.rag.service.document_service.document_dao.get_live_for_update',
        fake_get_for_update,
    )

    updated = asyncio.run(
        DocumentService.mark_index_failure(
            db=object(),
            document_id=7,
            index_version=3,
            status=DocumentStatus.FAILED,
            error_message='new failure',
        )
    )

    assert updated is False
    assert document.status == status
    assert document.error_message == 'existing'
