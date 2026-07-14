from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy_crud_plus import CRUDPlus

from backend.app.rag.model import Chunk, Document, KnowledgeBase


class CRUDKnowledgeBase(CRUDPlus[KnowledgeBase]):
    async def get_authorized(self, db: AsyncSession, *, pk: int, user_id: int, is_admin: bool, write: bool = False) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(KnowledgeBase.id == pk, KnowledgeBase.deleted == 0)
        if not is_admin:
            stmt = stmt.where(KnowledgeBase.owner_id == user_id if write else ((KnowledgeBase.owner_id == user_id) | KnowledgeBase.is_public))
        return await db.scalar(stmt)

    async def get_all_authorized(self, db: AsyncSession, *, user_id: int, is_admin: bool) -> list[KnowledgeBase]:
        stmt = select(KnowledgeBase).where(KnowledgeBase.deleted == 0).order_by(KnowledgeBase.id.desc())
        if not is_admin:
            stmt = stmt.where((KnowledgeBase.owner_id == user_id) | KnowledgeBase.is_public)
        return list((await db.scalars(stmt)).all())


class CRUDDocument(CRUDPlus[Document]):
    async def get_in_kb(self, db: AsyncSession, *, pk: int, knowledge_base_id: int) -> Document | None:
        return await db.scalar(select(Document).where(Document.id == pk, Document.knowledge_base_id == knowledge_base_id, Document.deleted == 0))

    async def get_list(self, db: AsyncSession, *, knowledge_base_id: int) -> list[Document]:
        result = await db.scalars(
            select(Document).where(Document.knowledge_base_id == knowledge_base_id, Document.deleted == 0).order_by(Document.id.desc())
        )
        return list(result.all())


class CRUDChunk(CRUDPlus[Chunk]):
    async def get_list(self, db: AsyncSession, *, document_id: int) -> list[Chunk]:
        result = await db.scalars(select(Chunk).where(Chunk.document_id == document_id, Chunk.deleted == 0).order_by(Chunk.chunk_index))
        return list(result.all())


knowledge_base_dao = CRUDKnowledgeBase(KnowledgeBase)
document_dao = CRUDDocument(Document)
chunk_dao = CRUDChunk(Chunk)
