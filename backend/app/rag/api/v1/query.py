from fastapi import APIRouter, Request

from backend.app.rag.schema.query import AnswerParam, GetAnswerDetail, GetSourceDetail, RetrieveParam
from backend.app.rag.service.query_service import query_service
from backend.common.response.response_schema import ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.database.db import CurrentSession, CurrentSessionTransaction

router = APIRouter(prefix='/rag', tags=['RAG 检索与问答'])


@router.post('/retrieve', summary='混合检索知识库', dependencies=[DependsJwtAuth])
async def retrieve_knowledge(db: CurrentSession, request: Request, obj: RetrieveParam) -> ResponseSchemaModel[list[GetSourceDetail]]:
    return response_base.success(data=await query_service.retrieve(db=db, user_id=request.user.id, is_admin=bool(request.user.is_superuser), obj=obj))


@router.post('/answer', summary='基于知识库问答', dependencies=[DependsJwtAuth])
async def answer_knowledge(db: CurrentSessionTransaction, request: Request, obj: AnswerParam) -> ResponseSchemaModel[GetAnswerDetail]:
    return response_base.success(data=await query_service.answer(db=db, user_id=request.user.id, is_admin=bool(request.user.is_superuser), obj=obj))
