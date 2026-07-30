import asyncio

from types import SimpleNamespace
from typing import Any

import pytest

from pytest import MonkeyPatch
from sqlalchemy.dialects import postgresql

from backend.app.rag.crud.crud_rag import chunk_dao, document_dao, knowledge_base_dao
from backend.app.rag.enums import DocumentStatus
from backend.app.rag.service.document_service import DocumentService
from backend.app.rag.service.knowledge_base_service import KnowledgeBaseService
from backend.common.exception import errors


class Database:
    def __init__(self) -> None:
        self.statement = None

    async def scalar(self, statement: Any) -> None:
        await asyncio.sleep(0)
        self.statement = statement


def _compiled_sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))


def test_private_knowledge_base_read_scope_allows_owner_or_public() -> None:
    db = Database()
    asyncio.run(knowledge_base_dao.get_authorized(db, pk=9, user_id=5, is_admin=False))
    sql = _compiled_sql(db.statement)
    assert 'rag_knowledge_base.owner_id = 5 OR rag_knowledge_base.is_public' in sql


def test_private_knowledge_base_write_scope_excludes_public_read_permission() -> None:
    db = Database()
    asyncio.run(knowledge_base_dao.get_authorized(db, pk=9, user_id=5, is_admin=False, write=True))
    sql = _compiled_sql(db.statement)
    assert 'rag_knowledge_base.owner_id = 5' in sql
    assert ' OR rag_knowledge_base.is_public' not in sql


def _make_document() -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        status=DocumentStatus.FAILED,
        error_message='索引失败',
        index_version=1,
        index_profile_id=10,
    )


def _capture_knowledge_base_scope(monkeypatch: MonkeyPatch, captured_scopes: list[dict[str, Any]]) -> None:
    async def fake_kb_get(**kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        captured_scopes.append(kwargs)
        return SimpleNamespace(id=3)

    monkeypatch.setattr(KnowledgeBaseService, 'get', staticmethod(fake_kb_get))


def test_document_retry_requires_knowledge_base_write_scope(monkeypatch: MonkeyPatch) -> None:
    captured_scopes: list[dict[str, Any]] = []
    document = _make_document()
    queued: list[tuple[int, int]] = []

    async def fake_get_in_kb(_db: Any, *, pk: int, knowledge_base_id: int) -> SimpleNamespace:
        await asyncio.sleep(0)
        return document

    async def fake_profile(**_kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        return SimpleNamespace(id=42)

    async def fake_enqueue_index(**kwargs: Any) -> None:
        await asyncio.sleep(0)
        queued.append((kwargs['document_id'], kwargs['index_version']))

    _capture_knowledge_base_scope(monkeypatch, captured_scopes)
    monkeypatch.setattr(document_dao, 'get_in_kb', fake_get_in_kb)
    monkeypatch.setattr('backend.app.rag.service.document_service.get_or_create_index_profile', fake_profile)
    monkeypatch.setattr('backend.app.rag.service.document_service.enqueue_document_index', fake_enqueue_index)

    asyncio.run(DocumentService.retry(db=object(), knowledge_base_id=3, pk=7, user_id=1, is_admin=False))

    assert [scope.get('write', False) for scope in captured_scopes] == [True]
    assert document.status == DocumentStatus.PENDING
    assert document.index_version == 2
    assert queued == [(7, 2)]


def test_document_delete_requires_knowledge_base_write_scope(monkeypatch: MonkeyPatch) -> None:
    captured_scopes: list[dict[str, Any]] = []
    document = _make_document()
    queued: list[int] = []

    async def fake_get_in_kb(_db: Any, *, pk: int, knowledge_base_id: int) -> SimpleNamespace:
        await asyncio.sleep(0)
        return document

    async def fake_enqueue_delete(**kwargs: Any) -> None:
        await asyncio.sleep(0)
        queued.append(kwargs['document_id'])

    _capture_knowledge_base_scope(monkeypatch, captured_scopes)
    monkeypatch.setattr(document_dao, 'get_in_kb', fake_get_in_kb)
    monkeypatch.setattr('backend.app.rag.service.document_service.enqueue_document_delete', fake_enqueue_delete)

    asyncio.run(DocumentService.delete(db=object(), knowledge_base_id=3, pk=7, user_id=1, is_admin=False))

    assert [scope.get('write', False) for scope in captured_scopes] == [True]
    assert document.status == DocumentStatus.DELETING
    assert queued == [7]


def test_document_read_paths_keep_knowledge_base_read_scope(monkeypatch: MonkeyPatch) -> None:
    captured_scopes: list[dict[str, Any]] = []
    document = _make_document()

    async def fake_get_in_kb(_db: Any, *, pk: int, knowledge_base_id: int) -> SimpleNamespace:
        await asyncio.sleep(0)
        return document

    async def fake_document_list(_db: Any, *, knowledge_base_id: int) -> list[SimpleNamespace]:
        await asyncio.sleep(0)
        return [document]

    async def fake_chunk_list(_db: Any, *, document_id: int) -> list[SimpleNamespace]:
        await asyncio.sleep(0)
        return []

    _capture_knowledge_base_scope(monkeypatch, captured_scopes)
    monkeypatch.setattr(document_dao, 'get_in_kb', fake_get_in_kb)
    monkeypatch.setattr(document_dao, 'get_list', fake_document_list)
    monkeypatch.setattr(chunk_dao, 'get_list', fake_chunk_list)

    asyncio.run(DocumentService.get_list(db=object(), knowledge_base_id=3, user_id=1, is_admin=False))
    asyncio.run(DocumentService.get_chunks(db=object(), knowledge_base_id=3, pk=7, user_id=1, is_admin=False))
    asyncio.run(DocumentService.get(db=object(), knowledge_base_id=3, pk=7, user_id=1, is_admin=False))

    assert [scope.get('write', False) for scope in captured_scopes] == [False, False, False]


def test_document_retry_denied_by_knowledge_base_scope_has_no_side_effects(monkeypatch: MonkeyPatch) -> None:
    document = _make_document()
    queued: list[int] = []

    async def fake_kb_get(**_kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        raise errors.NotFoundError(msg='知识库不存在或无权访问')

    async def fake_get_in_kb(_db: Any, *, pk: int, knowledge_base_id: int) -> SimpleNamespace:
        await asyncio.sleep(0)
        return document

    async def fake_enqueue_index(**kwargs: Any) -> None:
        await asyncio.sleep(0)
        queued.append(kwargs['document_id'])

    monkeypatch.setattr(KnowledgeBaseService, 'get', staticmethod(fake_kb_get))
    monkeypatch.setattr(document_dao, 'get_in_kb', fake_get_in_kb)
    monkeypatch.setattr('backend.app.rag.service.document_service.enqueue_document_index', fake_enqueue_index)

    with pytest.raises(errors.NotFoundError):
        asyncio.run(DocumentService.retry(db=object(), knowledge_base_id=3, pk=7, user_id=2, is_admin=False))

    assert document.status == DocumentStatus.FAILED
    assert document.index_version == 1
    assert queued == []


def test_document_delete_denied_by_knowledge_base_scope_has_no_side_effects(monkeypatch: MonkeyPatch) -> None:
    document = _make_document()
    queued: list[int] = []

    async def fake_kb_get(**_kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(0)
        raise errors.NotFoundError(msg='知识库不存在或无权访问')

    async def fake_get_in_kb(_db: Any, *, pk: int, knowledge_base_id: int) -> SimpleNamespace:
        await asyncio.sleep(0)
        return document

    async def fake_enqueue_delete(**kwargs: Any) -> None:
        await asyncio.sleep(0)
        queued.append(kwargs['document_id'])

    monkeypatch.setattr(KnowledgeBaseService, 'get', staticmethod(fake_kb_get))
    monkeypatch.setattr(document_dao, 'get_in_kb', fake_get_in_kb)
    monkeypatch.setattr('backend.app.rag.service.document_service.enqueue_document_delete', fake_enqueue_delete)

    with pytest.raises(errors.NotFoundError):
        asyncio.run(DocumentService.delete(db=object(), knowledge_base_id=3, pk=7, user_id=2, is_admin=False))

    assert document.status == DocumentStatus.FAILED
    assert queued == []
