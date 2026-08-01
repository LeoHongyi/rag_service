import json

from datetime import timedelta

from celery import Task  # type: ignore[import-untyped]
from sqlalchemy import delete, select

from backend.app.rag.adapters.storage import storage
from backend.app.rag.enums import DocumentStatus
from backend.app.rag.indexing import index_retry_countdown, is_retryable_index_error, sanitize_index_error
from backend.app.rag.model import Chunk, Document, OutboxEvent
from backend.app.rag.service.document_service import document_service
from backend.app.rag.service.outbox_service import (
    DELETE_DOCUMENT_EVENT,
    INDEX_DOCUMENT_EVENT,
    claim_pending_events,
    mark_dispatched,
    mark_failed,
)
from backend.app.task.celery import celery_app
from backend.core.conf import settings
from backend.database.db import async_db_session
from backend.utils.timezone import timezone


def _dispatch_event(event: OutboxEvent) -> None:
    """投递单个已锁定事件；失败状态留给下一轮重试。"""
    try:
        payload = json.loads(event.payload)
        if event.event_type == INDEX_DOCUMENT_EVENT:
            index_document.delay(payload['document_id'], payload['index_version'])
        elif event.event_type == DELETE_DOCUMENT_EVENT:
            delete_document.delay(payload['document_id'])
        else:
            raise ValueError(f'不支持的 Outbox 事件类型: {event.event_type}')
        mark_dispatched(event=event)
    except Exception as exc:
        mark_failed(event=event, exc=exc, max_attempts=settings.RAG_OUTBOX_MAX_DISPATCH_ATTEMPTS)


@celery_app.task(
    bind=True,
    name='rag_index_document',
    autoretry_for=(),
    max_retries=settings.RAG_INDEX_MAX_RETRIES,
    acks_late=True,
    reject_on_worker_lost=True,
)
async def index_document(task: Task, document_id: int, index_version: int | None = None) -> str:
    """在请求路径外解析、切分并向量化文档。"""
    async with async_db_session.begin() as db:
        claim_result, effective_version = await document_service.claim_index(
            db=db,
            document_id=document_id,
            index_version=index_version,
        )
    if claim_result != 'claimed' or effective_version is None:
        return claim_result

    try:
        async with async_db_session.begin() as db:
            return await document_service.index_claimed_document(
                db=db,
                document_id=document_id,
                index_version=effective_version,
            )
    except Exception as exc:
        retries = int(task.request.retries)
        max_retries = int(task.max_retries or 0)
        retryable = is_retryable_index_error(exc)
        should_retry = retryable and retries < max_retries
        failure_status = DocumentStatus.PENDING if should_retry else DocumentStatus.FAILED
        error_message = sanitize_index_error(exc)
        async with async_db_session.begin() as db:
            await document_service.mark_index_failure(
                db=db,
                document_id=document_id,
                index_version=effective_version,
                status=failure_status,
                error_message=error_message,
            )
        if should_retry:
            countdown = index_retry_countdown(
                retries=retries,
                max_seconds=settings.RAG_INDEX_RETRY_BACKOFF_MAX_SECONDS,
            )
            raise task.retry(exc=exc, countdown=countdown)
        if retryable:
            raise
        return DocumentStatus.FAILED.value


@celery_app.task(name='rag_delete_document', autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
async def delete_document(document_id: int) -> str:
    """异步清理原始对象和切片；重复投递安全且失败后保持 DELETING。"""
    async with async_db_session.begin() as db:
        # 取行锁：Beat 的补偿投递、Outbox 原始投递与 OSError 自动重试都可能同时到达。
        # 无锁时两个任务会双双通过 DELETING 检查并各自执行硬删除，落后的一方
        # 因删除 0 行而抛 StaleDataError，产生虚假的任务失败告警。
        document = await db.scalar(
            select(Document).where(Document.id == document_id, Document.deleted == 0).with_for_update()
        )
        if not document:
            return 'document_not_found'
        if document.status != DocumentStatus.DELETING:
            return 'delete_not_requested'
        storage.delete(key=document.storage_key)
        await db.execute(delete(Chunk).where(Chunk.document_id == document.id))
        await db.delete(document)
        return 'deleted'


@celery_app.task(name='rag_dispatch_outbox')
async def dispatch_outbox(limit: int = 100) -> str:
    """在独立事务中投递已提交的 RAG Outbox 事件。"""
    async with async_db_session.begin() as db:
        events = await claim_pending_events(db=db, limit=limit)
        for event in events:
            _dispatch_event(event)
        return f'dispatched={sum(event.status.value == "DISPATCHED" for event in events)}'


@celery_app.task(name='rag_repair_stuck_document')
async def repair_stuck_document() -> str:
    """恢复超时索引，并重新投递未完成的删除补偿任务。"""
    stale_before = timezone.now() - timedelta(seconds=settings.RAG_INDEX_STALE_SECONDS)
    async with async_db_session.begin() as db:
        recovered = await document_service.recover_stale_indexes(
            db=db,
            stale_before=stale_before,
            limit=100,
        )
        deleting_document_ids = await document_service.get_deleting_document_ids(db=db)
    for document_id, index_version in recovered:
        index_document.delay(document_id, index_version)
    for document_id in deleting_document_ids:
        delete_document.delay(document_id)
    return f'requeued_indexes={len(recovered)},requeued_deletions={len(deleting_document_ids)}'
