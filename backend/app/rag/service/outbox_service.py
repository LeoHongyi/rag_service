import json

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rag.enums import OutboxStatus
from backend.app.rag.indexing import sanitize_dispatch_error
from backend.app.rag.model import OutboxEvent
from backend.common.log import log

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
    """锁定一批待投递事件，支持多个 dispatcher 并发运行。

    只认领 PENDING 与 FAILED；DEAD 与 DISPATCHED 被排除，避免无法成功的事件
    永久占用每轮固定大小的批次。
    """
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


def mark_failed(*, event: OutboxEvent, exc: Exception, max_attempts: int) -> None:
    """记录投递失败；超过上限后转入 DEAD，不再参与后续认领。

    `dispatch_attempts` 此前只写不读，意味着永远不会成功的事件（载荷损坏、
    事件类型未知）会每隔一个调度周期被重试一次。由于认领是
    `ORDER BY id LIMIT n`，这类事件累积到批次容量后会持续挤占名额，
    使新事件迟迟得不到投递。
    """
    event.dispatch_attempts += 1
    event.status = OutboxStatus.DEAD if event.dispatch_attempts >= max_attempts else OutboxStatus.FAILED
    event.last_error = sanitize_dispatch_error(exc)[:512]
    if event.status == OutboxStatus.DEAD:
        log.error(
            'RAG Outbox 事件投递失败次数达到上限，已转入 DEAD：event_id=%s type=%s attempts=%s',
            event.id,
            event.event_type,
            event.dispatch_attempts,
        )
