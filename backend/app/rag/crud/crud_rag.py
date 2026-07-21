from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_crud_plus import CRUDPlus

from backend.app.rag.enums import DocumentStatus
from backend.app.rag.model import Chunk, Document, KnowledgeBase


class CRUDKnowledgeBase(CRUDPlus[KnowledgeBase]):
    async def get_authorized(
        self,
        db: AsyncSession,
        *,
        pk: int,
        user_id: int,
        is_admin: bool,
        write: bool = False,
    ) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(KnowledgeBase.id == pk, KnowledgeBase.deleted == 0)
        if not is_admin:
            authorized = (
                KnowledgeBase.owner_id == user_id
                if write
                else (KnowledgeBase.owner_id == user_id) | KnowledgeBase.is_public
            )
            stmt = stmt.where(authorized)
        return await db.scalar(stmt)

    async def get_all_authorized(self, db: AsyncSession, *, user_id: int, is_admin: bool) -> list[KnowledgeBase]:
        stmt = select(KnowledgeBase).where(KnowledgeBase.deleted == 0).order_by(KnowledgeBase.id.desc())
        if not is_admin:
            stmt = stmt.where((KnowledgeBase.owner_id == user_id) | KnowledgeBase.is_public)
        return list((await db.scalars(stmt)).all())


class CRUDDocument(CRUDPlus[Document]):
    async def get_live(self, db: AsyncSession, *, pk: int) -> Document | None:
        return await db.scalar(select(Document).where(Document.id == pk, Document.deleted == 0))

    async def get_live_for_update(self, db: AsyncSession, *, pk: int) -> Document | None:
        stmt = select(Document).where(Document.id == pk, Document.deleted == 0).with_for_update()
        return await db.scalar(stmt)

    async def get_in_kb(self, db: AsyncSession, *, pk: int, knowledge_base_id: int) -> Document | None:
        stmt = select(Document).where(
            Document.id == pk,
            Document.knowledge_base_id == knowledge_base_id,
            Document.deleted == 0,
        )
        return await db.scalar(stmt)

    async def get_list(self, db: AsyncSession, *, knowledge_base_id: int) -> list[Document]:
        result = await db.scalars(
            select(Document)
            .where(Document.knowledge_base_id == knowledge_base_id, Document.deleted == 0)
            .order_by(Document.id.desc())
        )
        return list(result.all())

    async def get_ids_by_status(self, db: AsyncSession, *, status: str) -> list[int]:
        stmt = select(Document.id).where(Document.status == status, Document.deleted == 0)
        return list((await db.scalars(stmt)).all())

    async def get_stale_index_documents(
        self,
        db: AsyncSession,
        *,
        stale_before: datetime,
        limit: int,
    ) -> list[Document]:
        last_activity = func.coalesce(Document.updated_time, Document.created_time)
        stmt = (
            select(Document)
            .where(
                Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING]),
                Document.deleted == 0,
                last_activity < stale_before,
            )
            .order_by(last_activity, Document.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await db.scalars(stmt)).all())


class CRUDChunk(CRUDPlus[Chunk]):
    async def get_list(self, db: AsyncSession, *, document_id: int) -> list[Chunk]:
        stmt = select(Chunk).where(Chunk.document_id == document_id, Chunk.deleted == 0).order_by(Chunk.chunk_index)
        result = await db.scalars(stmt)
        return list(result.all())


knowledge_base_dao = CRUDKnowledgeBase(KnowledgeBase)
document_dao = CRUDDocument(Document)
chunk_dao = CRUDChunk(Chunk)
