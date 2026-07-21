import json

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rag.enums import OutboxStatus
from backend.app.rag.model import OutboxEvent

INDEX_DOCUMENT_EVENT = 'rag.document.index.requested'
DELETE_DOCUMENT_EVENT = 'rag.document.delete.requested'


async def enqueue_document_index(*, db: AsyncSession, document_id: int, index_version: int) -> OutboxEvent:
    """把索引请求写入当前数据库事务，避免事务内直接投递 Celery。"""
    dedupe_key = f'{document_id}:{index_version}'
    event = await db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.event_type == INDEX_DOCUMENT_EVENT,
            OutboxEvent.aggregate_id == document_id,
            OutboxEvent.dedupe_key == dedupe_key,
        )
    )
    if event:
        return event
    event = OutboxEvent(
        event_type=INDEX_DOCUMENT_EVENT,
        aggregate_id=document_id,
        payload=json.dumps({'document_id': document_id, 'index_version': index_version}),
        dedupe_key=dedupe_key,
    )
    db.add(event)
    await db.flush()
    return event


async def enqueue_document_delete(*, db: AsyncSession, document_id: int) -> OutboxEvent:
    """把删除对象与切片的补偿任务写入当前事务。"""
    dedupe_key = str(document_id)
    event = await db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.event_type == DELETE_DOCUMENT_EVENT,
            OutboxEvent.aggregate_id == document_id,
            OutboxEvent.dedupe_key == dedupe_key,
        )
    )
    if event:
        return event
    event = OutboxEvent(
        event_type=DELETE_DOCUMENT_EVENT,
        aggregate_id=document_id,
        payload=json.dumps({'document_id': document_id}),
        dedupe_key=dedupe_key,
    )
    db.add(event)
    await db.flush()
    return event


async def claim_pending_events(*, db: AsyncSession, limit: int) -> list[OutboxEvent]:
    """锁定一批待投递事件，支持多个 dispatcher 并发运行。"""
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.status.in_([OutboxStatus.PENDING, OutboxStatus.FAILED]))
        .order_by(OutboxEvent.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list((await db.scalars(stmt)).all())


def mark_dispatched(*, event: OutboxEvent) -> None:
    """记录成功投递。"""
    event.status = OutboxStatus.DISPATCHED
    event.dispatch_attempts += 1
    event.last_error = None
    event.dispatched_time = datetime.now().astimezone()


def mark_failed(*, event: OutboxEvent, exc: Exception) -> None:
    """保留失败事件供下一次 dispatcher 重试。"""
    event.status = OutboxStatus.FAILED
    event.dispatch_attempts += 1
    event.last_error = str(exc)[:512]
