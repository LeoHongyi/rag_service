from backend.app.task.celery import celery_app
from backend.app.rag.adapters.storage import storage
from backend.app.rag.enums import DocumentStatus
from backend.app.rag.model import Document
from backend.app.rag.service.document_service import document_service
from backend.database.db import async_db_session
from sqlalchemy import select


@celery_app.task(name='rag_index_document', autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
async def index_document(document_id: int) -> str:
    """Parse, chunk and embed an uploaded document outside the request path."""
    async with async_db_session.begin() as db:
        document = await db.scalar(select(Document).where(Document.id == document_id, Document.deleted == 0))
        if not document or document.deleted:
            return 'document_not_found'
        if document.status == DocumentStatus.READY:
            return 'already_ready'
        try:
            content = storage.get(key=document.storage_key)
            await document_service.index_content(db=db, document=document, content=content)
        except Exception as exc:
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)[:512]
            raise
        return document.status.value


@celery_app.task(name='rag_repair_stuck_document')
async def repair_stuck_document() -> str:
    """Keep a named maintenance hook for scheduled stale-job repair."""
    return 'ok'
