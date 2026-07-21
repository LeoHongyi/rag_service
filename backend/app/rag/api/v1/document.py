from typing import Annotated

from fastapi import APIRouter, File, Path, Request, UploadFile

from backend.app.rag.schema.document import GetChunkDetail, GetDocumentDetail
from backend.app.rag.service.document_service import document_service
from backend.common.response.response_schema import ResponseSchemaModel, response_base
from backend.common.security.jwt import DependsJwtAuth
from backend.database.db import CurrentSession, CurrentSessionTransaction

router = APIRouter(prefix='/rag/knowledge-bases/{knowledge_base_id}/documents', tags=['RAG 文档'])


@router.get('', summary='获取知识库文档', dependencies=[DependsJwtAuth])
async def get_documents(
    db: CurrentSession, request: Request, knowledge_base_id: Annotated[int, Path(description='知识库 ID')]
) -> ResponseSchemaModel[list[GetDocumentDetail]]:
    return response_base.success(
        data=await document_service.get_list(
            db=db,
            knowledge_base_id=knowledge_base_id,
            user_id=request.user.id,
            is_admin=bool(request.user.is_superuser),
        )
    )


@router.post('', summary='上传并索引文档', dependencies=[DependsJwtAuth])
async def create_document(
    db: CurrentSessionTransaction,
    request: Request,
    knowledge_base_id: Annotated[int, Path(description='知识库 ID')],
    file: Annotated[UploadFile, File(description='知识库文件')],
) -> ResponseSchemaModel[GetDocumentDetail]:
    content = await file.read()
    return response_base.success(
        data=await document_service.create(
            db=db,
            knowledge_base_id=knowledge_base_id,
            user_id=request.user.id,
            is_admin=bool(request.user.is_superuser),
            filename=file.filename or 'upload.txt',
            content=content,
            mime_type=file.content_type,
        )
    )


@router.get('/{pk}/chunks', summary='获取文档切片', dependencies=[DependsJwtAuth])
async def get_document_chunks(
    db: CurrentSession,
    request: Request,
    knowledge_base_id: Annotated[int, Path(description='知识库 ID')],
    pk: Annotated[int, Path(description='文档 ID')],
) -> ResponseSchemaModel[list[GetChunkDetail]]:
    return response_base.success(
        data=await document_service.get_chunks(
            db=db,
            knowledge_base_id=knowledge_base_id,
            pk=pk,
            user_id=request.user.id,
            is_admin=bool(request.user.is_superuser),
        )
    )


@router.get('/{pk}', summary='获取文档详情', dependencies=[DependsJwtAuth])
async def get_document(
    db: CurrentSession,
    request: Request,
    knowledge_base_id: Annotated[int, Path(description='知识库 ID')],
    pk: Annotated[int, Path(description='文档 ID')],
) -> ResponseSchemaModel[GetDocumentDetail]:
    return response_base.success(
        data=await document_service.get(
            db=db,
            knowledge_base_id=knowledge_base_id,
            pk=pk,
            user_id=request.user.id,
            is_admin=bool(request.user.is_superuser),
        )
    )


@router.post('/{pk}/retry', summary='重试索引文档', dependencies=[DependsJwtAuth])
async def retry_document(
    db: CurrentSessionTransaction,
    request: Request,
    knowledge_base_id: Annotated[int, Path(description='知识库 ID')],
    pk: Annotated[int, Path(description='文档 ID')],
) -> ResponseSchemaModel[GetDocumentDetail]:
    return response_base.success(
        data=await document_service.retry(
            db=db,
            knowledge_base_id=knowledge_base_id,
            pk=pk,
            user_id=request.user.id,
            is_admin=bool(request.user.is_superuser),
        )
    )


@router.delete('/{pk}', summary='删除文档', dependencies=[DependsJwtAuth])
async def delete_document(
    db: CurrentSessionTransaction,
    request: Request,
    knowledge_base_id: Annotated[int, Path(description='知识库 ID')],
    pk: Annotated[int, Path(description='文档 ID')],
) -> ResponseSchemaModel[None]:
    await document_service.delete(
        db=db,
        knowledge_base_id=knowledge_base_id,
        pk=pk,
        user_id=request.user.id,
        is_admin=bool(request.user.is_superuser),
    )
    return response_base.success()
