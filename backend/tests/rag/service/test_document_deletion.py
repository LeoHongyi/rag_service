import asyncio

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

from pytest import MonkeyPatch

from backend.app.rag.enums import DocumentStatus
from backend.app.rag.service.document_service import DocumentService
from backend.app.rag.service.knowledge_base_service import KnowledgeBaseService


def test_document_delete_queues_compensation_instead_of_deleting_storage(monkeypatch: MonkeyPatch) -> None:
    document = SimpleNamespace(id=7, status=DocumentStatus.READY)
    queued: list[int] = []

    async def fake_get(**_kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        return document

    async def fake_enqueue(**kwargs: Any) -> None:
        await asyncio.sleep(0)
        queued.append(kwargs['document_id'])

    monkeypatch.setattr(DocumentService, 'get', staticmethod(fake_get))
    monkeypatch.setattr('backend.app.rag.service.document_service.enqueue_document_delete', fake_enqueue)

    asyncio.run(DocumentService.delete(db=object(), knowledge_base_id=3, pk=7, user_id=1, is_admin=False))

    assert document.status == DocumentStatus.DELETING
    assert queued == [7]


def test_knowledge_base_delete_queues_every_live_document(monkeypatch: MonkeyPatch) -> None:
    knowledge_base = SimpleNamespace(id=3, deleted=0)
    documents = [
        SimpleNamespace(id=7, status=DocumentStatus.READY),
        SimpleNamespace(id=8, status=DocumentStatus.FAILED),
    ]
    queued: list[int] = []

    class ScalarResult:
        def __iter__(self) -> Iterator[SimpleNamespace]:
            return iter(documents)

    class Database:
        async def scalars(self, _statement: Any) -> ScalarResult:
            await asyncio.sleep(0)
            return ScalarResult()

    async def fake_get(**_kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        return knowledge_base

    async def fake_enqueue(**kwargs: Any) -> None:
        await asyncio.sleep(0)
        queued.append(kwargs['document_id'])

    monkeypatch.setattr(KnowledgeBaseService, 'get', staticmethod(fake_get))
    monkeypatch.setattr('backend.app.rag.service.knowledge_base_service.enqueue_document_delete', fake_enqueue)

    asyncio.run(KnowledgeBaseService.delete(db=Database(), pk=3, user_id=1, is_admin=False))

    assert knowledge_base.deleted == 3
    assert [document.status for document in documents] == [DocumentStatus.DELETING, DocumentStatus.DELETING]
    assert queued == [7, 8]
