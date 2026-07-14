from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rag.crud.crud_rag import knowledge_base_dao
from backend.app.rag.model import KnowledgeBase
from backend.app.rag.schema.knowledge_base import CreateKnowledgeBaseParam, UpdateKnowledgeBaseParam
from backend.common.exception import errors


class KnowledgeBaseService:
    @staticmethod
    async def get(*, db: AsyncSession, pk: int, user_id: int, is_admin: bool, write: bool = False) -> KnowledgeBase:
        data = await knowledge_base_dao.get_authorized(db, pk=pk, user_id=user_id, is_admin=is_admin, write=write)
        if not data:
            raise errors.NotFoundError(msg='知识库不存在或无权访问')
        return data

    @staticmethod
    async def get_all(*, db: AsyncSession, user_id: int, is_admin: bool) -> list[KnowledgeBase]:
        return await knowledge_base_dao.get_all_authorized(db, user_id=user_id, is_admin=is_admin)

    @staticmethod
    async def create(*, db: AsyncSession, user_id: int, obj: CreateKnowledgeBaseParam) -> KnowledgeBase:
        data = KnowledgeBase(owner_id=user_id, name=obj.name.strip(), description=obj.description, is_public=obj.is_public)
        db.add(data)
        await db.flush()
        return data

    @staticmethod
    async def update(*, db: AsyncSession, pk: int, user_id: int, is_admin: bool, obj: UpdateKnowledgeBaseParam) -> KnowledgeBase:
        data = await KnowledgeBaseService.get(db=db, pk=pk, user_id=user_id, is_admin=is_admin, write=True)
        for key, value in obj.model_dump(exclude_unset=True).items():
            setattr(data, key, value.strip() if key == 'name' and value else value)
        return data

    @staticmethod
    async def delete(*, db: AsyncSession, pk: int, user_id: int, is_admin: bool) -> None:
        data = await KnowledgeBaseService.get(db=db, pk=pk, user_id=user_id, is_admin=is_admin, write=True)
        data.deleted = data.id


knowledge_base_service = KnowledgeBaseService()
