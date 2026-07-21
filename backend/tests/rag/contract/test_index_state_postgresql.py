import asyncio
import os

from datetime import timedelta
from uuid import uuid4

import pytest

from backend.app.rag.enums import DocumentStatus
from backend.app.rag.model import Document, KnowledgeBase
from backend.app.rag.service.document_service import document_service
from backend.core.conf import settings
from backend.database.db import async_db_session
from backend.utils.timezone import timezone

pytestmark = pytest.mark.skipif(
    os.getenv('RAG_RUN_POSTGRES_INTEGRATION') != '1',
    reason='需要显式启用 PostgreSQL 集成验证',
)


def test_claim_and_recover_stale_index_in_postgresql() -> None:
    async def run() -> None:
        async with async_db_session() as db:
            transaction = await db.begin()
            try:
                knowledge_base = KnowledgeBase(
                    owner_id=9_000_001,
                    name=f'index-state-{uuid4().hex}',
                )
                db.add(knowledge_base)
                await db.flush()
                document = Document(
                    knowledge_base_id=knowledge_base.id,
                    filename='recovery.txt',
                    file_type='txt',
                    storage_key=f'integration/{uuid4().hex}.txt',
                    file_size=8,
                    content_hash=uuid4().hex,
                )
                db.add(document)
                await db.flush()
                await db.refresh(document)

                claim_result, index_version = await document_service.claim_index(
                    db=db,
                    document_id=document.id,
                    index_version=document.index_version,
                )
                assert claim_result == 'claimed'
                assert index_version == document.index_version
                assert document.status == DocumentStatus.PROCESSING

                duplicate_result, _ = await document_service.claim_index(
                    db=db,
                    document_id=document.id,
                    index_version=document.index_version,
                )
                assert duplicate_result == 'already_processing'

                document.updated_time = timezone.now() - timedelta(seconds=settings.RAG_INDEX_STALE_SECONDS + 1)
                await db.flush()
                recovered = await document_service.recover_stale_indexes(
                    db=db,
                    stale_before=timezone.now() - timedelta(seconds=settings.RAG_INDEX_STALE_SECONDS),
                    limit=10,
                )
                assert recovered == [(document.id, document.index_version)]
                assert document.status == DocumentStatus.PENDING
                assert document.error_message == '索引任务超时，已重新排队'
            finally:
                await transaction.rollback()

    asyncio.run(run())
