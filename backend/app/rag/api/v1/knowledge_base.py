from typing import Annotated

from fastapi import APIRouter, Path, Request

from backend.app.rag.schema.knowledge_base import CreateKnowledgeBaseParam, GetKnowledgeBaseDetail, UpdateKnowledgeBaseParam
from backend.app.rag.service.knowledge_base_service import knowledge_base_service
from backend.common.response.response_schema import ResponseModel, ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.database.db import CurrentSession, CurrentSessionTransaction

router = APIRouter(prefix='/rag/knowledge-bases', tags=['RAG 知识库'])


def _identity(request: Request) -> tuple[int, bool]:
    return request.user.id, bool(request.user.is_superuser)


@router.get('/all', summary='获取可访问知识库', dependencies=[DependsJwtAuth])
async def get_all_knowledge_bases(db: CurrentSession, request: Request) -> ResponseSchemaModel[list[GetKnowledgeBaseDetail]]:
    user_id, is_admin = _identity(request)
    return response_base.success(data=await knowledge_base_service.get_all(db=db, user_id=user_id, is_admin=is_admin))


@router.get('/{pk}', summary='获取知识库详情', dependencies=[DependsJwtAuth])
async def get_knowledge_base(db: CurrentSession, request: Request, pk: Annotated[int, Path(description='知识库 ID')]) -> ResponseSchemaModel[GetKnowledgeBaseDetail]:
    user_id, is_admin = _identity(request)
    return response_base.success(data=await knowledge_base_service.get(db=db, pk=pk, user_id=user_id, is_admin=is_admin))


@router.post('', summary='创建知识库', dependencies=[DependsJwtAuth])
async def create_knowledge_base(db: CurrentSessionTransaction, request: Request, obj: CreateKnowledgeBaseParam) -> ResponseSchemaModel[GetKnowledgeBaseDetail]:
    user_id, _ = _identity(request)
    return response_base.success(data=await knowledge_base_service.create(db=db, user_id=user_id, obj=obj))


@router.put('/{pk}', summary='更新知识库', dependencies=[DependsJwtAuth])
async def update_knowledge_base(db: CurrentSessionTransaction, request: Request, pk: Annotated[int, Path(description='知识库 ID')], obj: UpdateKnowledgeBaseParam) -> ResponseSchemaModel[GetKnowledgeBaseDetail]:
    user_id, is_admin = _identity(request)
    return response_base.success(data=await knowledge_base_service.update(db=db, pk=pk, user_id=user_id, is_admin=is_admin, obj=obj))


@router.delete('/{pk}', summary='删除知识库', dependencies=[DependsJwtAuth])
async def delete_knowledge_base(db: CurrentSessionTransaction, request: Request, pk: Annotated[int, Path(description='知识库 ID')]) -> ResponseModel:
    user_id, is_admin = _identity(request)
    await knowledge_base_service.delete(db=db, pk=pk, user_id=user_id, is_admin=is_admin)
    return response_base.success()
