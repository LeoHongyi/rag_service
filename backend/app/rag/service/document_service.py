import hashlib

from datetime import datetime

import httpx

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rag.adapters.embedding import embedding_provider
from backend.app.rag.adapters.storage import storage
from backend.app.rag.chunking import contextualize_chunk, split_parent_child_text
from backend.app.rag.crud.crud_rag import chunk_dao, document_dao
from backend.app.rag.enums import DocumentStatus
from backend.app.rag.lexical import extract_exact_tokens, tokenize_search_text
from backend.app.rag.model import Chunk, Document
from backend.app.rag.parsers.text import SUPPORTED_DOCUMENT_SUFFIXES
from backend.app.rag.service.index_profile_service import get_or_create_index_profile
from backend.app.rag.service.knowledge_base_service import knowledge_base_service
from backend.app.rag.service.outbox_service import enqueue_document_delete, enqueue_document_index
from backend.common.exception import errors
from backend.core.conf import settings
from backend.utils.timezone import timezone


async def embed_texts_in_batches(*, texts: list[str], batch_size: int) -> list[list[float]]:
    """按供应商批量上限生成向量，保持输入与输出顺序一致。

    个别 OpenAI 兼容 Embedding 网关会因批请求大小或请求体内部校验返回
    HTTP 400。400 不是常规可重试错误，因此仅在批次包含多段文本时二分拆分；
    这样既能恢复批级失败，也能让无法被供应商接受的单段文本明确失败。
    """
    if batch_size < 1:
        raise ValueError('Embedding 批量大小必须大于 0')

    async def embed_batch(batch: list[str]) -> list[list[float]]:
        try:
            return await embedding_provider.embed(batch)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 400 or len(batch) == 1:
                raise
            midpoint = len(batch) // 2
            return await embed_batch(batch[:midpoint]) + await embed_batch(batch[midpoint:])

    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(await embed_batch(texts[start : start + batch_size]))
    return vectors


class DocumentService:
    @staticmethod
    async def create(
        *,
        db: AsyncSession,
        knowledge_base_id: int,
        user_id: int,
        is_admin: bool,
        filename: str,
        content: bytes,
        mime_type: str | None,
    ) -> Document:
        kb = await knowledge_base_service.get(
            db=db, pk=knowledge_base_id, user_id=user_id, is_admin=is_admin, write=True
        )
        suffix = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
            raise errors.RequestError(msg='仅支持 .txt、.md、.docx、.pdf 文件')
        if len(content) > settings.RAG_MAX_FILE_SIZE:
            raise errors.RequestError(msg=f'文件不能超过 {settings.RAG_MAX_FILE_SIZE // 1024 // 1024}MB')
        digest = hashlib.sha256(content).hexdigest()
        storage_key = f'{kb.id}/{digest}.{suffix}'
        storage.put(key=storage_key, content=content)
        profile = await get_or_create_index_profile(db=db)
        data = Document(
            knowledge_base_id=kb.id,
            filename=filename,
            file_type=suffix,
            mime_type=mime_type,
            storage_key=storage_key,
            file_size=len(content),
            content_hash=digest,
            index_profile_id=profile.id,
        )
        db.add(data)
        await db.flush()
        await enqueue_document_index(db=db, document_id=data.id, index_version=data.index_version)
        return data

    @staticmethod
    async def index_content(*, db: AsyncSession, document: Document, content: bytes) -> None:
        from backend.app.rag.parsers.text import parse_document

        document.status = DocumentStatus.PROCESSING
        text = parse_document(filename=document.filename, data=content)
        parent_children = split_parent_child_text(
            text=text, chunk_size=settings.RAG_CHUNK_SIZE, overlap=settings.RAG_CHUNK_OVERLAP
        )
        if not parent_children:
            raise ValueError('文档没有可索引正文')
        children = [(parent, child) for parent in parent_children for child in parent.children]
        contextualized_pieces = [
            contextualize_chunk(filename=document.filename, heading_path=parent.heading_path, content=child)
            for parent, child in children
        ]
        vectors = await embed_texts_in_batches(
            texts=contextualized_pieces,
            batch_size=settings.RAG_EMBEDDING_BATCH_SIZE,
        )

        await db.execute(delete(Chunk).where(Chunk.document_id == document.id))
        parents: list[Chunk] = []
        for parent_index, parent in enumerate(parent_children, start=1):
            parent_chunk = Chunk(
                knowledge_base_id=document.knowledge_base_id,
                document_id=document.id,
                chunk_index=-parent_index,
                content=parent.parent_content,
                contextual_content=contextualize_chunk(
                    filename=document.filename, heading_path=parent.heading_path, content=parent.parent_content
                ),
                search_text='',
                exact_tokens=[],
                content_hash=hashlib.sha256(parent.parent_content.encode()).hexdigest(),
                char_count=len(parent.parent_content),
                token_count=max(len(parent.parent_content) // 4, 1),
                embedding=None,
                index_version=document.index_version,
                is_parent=True,
                heading_path=parent.heading_path,
            )
            db.add(parent_chunk)
            parents.append(parent_chunk)
        await db.flush()
        parent_ids = {id(parent): chunk.id for parent, chunk in zip(parent_children, parents, strict=True)}
        for index, ((parent, piece), vector) in enumerate(zip(children, vectors, strict=True)):
            db.add(
                Chunk(
                    knowledge_base_id=document.knowledge_base_id,
                    document_id=document.id,
                    chunk_index=index,
                    content=piece,
                    contextual_content=contextualize_chunk(
                        filename=document.filename, heading_path=parent.heading_path, content=piece
                    ),
                    search_text=tokenize_search_text(contextualized_pieces[index]),
                    exact_tokens=extract_exact_tokens(contextualized_pieces[index]),
                    content_hash=hashlib.sha256(piece.encode()).hexdigest(),
                    char_count=len(piece),
                    token_count=max(len(piece) // 4, 1),
                    embedding=vector,
                    index_version=document.index_version,
                    parent_chunk_id=parent_ids[id(parent)],
                    heading_path=parent.heading_path,
                )
            )
        document.parsed_content = text
        document.chunk_count = len(children)
        document.status = DocumentStatus.READY
        document.error_message = None

    @staticmethod
    async def claim_index(
        *,
        db: AsyncSession,
        document_id: int,
        index_version: int | None,
    ) -> tuple[str, int | None]:
        """使用行锁抢占当前版本的待处理文档。"""
        document = await document_dao.get_live_for_update(db, pk=document_id)
        if not document:
            return 'document_not_found', None
        effective_version = document.index_version
        if index_version is not None and effective_version != index_version:
            return 'stale_index_request', effective_version
        if document.status == DocumentStatus.READY:
            return 'already_ready', effective_version
        if document.status == DocumentStatus.PROCESSING:
            return 'already_processing', effective_version
        if document.status == DocumentStatus.DELETING:
            return 'delete_requested', effective_version
        if document.status == DocumentStatus.FAILED:
            return 'index_failed', effective_version

        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        return 'claimed', effective_version

    @staticmethod
    async def index_claimed_document(
        *,
        db: AsyncSession,
        document_id: int,
        index_version: int,
    ) -> str:
        """索引已经由当前任务抢占的文档。"""
        document = await document_dao.get_live_for_update(db, pk=document_id)
        if not document:
            return 'document_not_found'
        if document.index_version != index_version:
            return 'stale_index_request'
        if document.status != DocumentStatus.PROCESSING:
            return f'index_not_processing:{document.status.value}'

        content = storage.get(key=document.storage_key)
        await DocumentService.index_content(db=db, document=document, content=content)
        return document.status.value

    @staticmethod
    async def mark_index_failure(
        *,
        db: AsyncSession,
        document_id: int,
        index_version: int,
        status: DocumentStatus,
        error_message: str,
    ) -> bool:
        """记录当前索引版本的重试或终态失败。"""
        if status not in {DocumentStatus.PENDING, DocumentStatus.FAILED}:
            raise ValueError('索引失败只能更新为 PENDING 或 FAILED')
        document = await document_dao.get_live_for_update(db, pk=document_id)
        if not document or document.index_version != index_version:
            return False
        if document.status in {DocumentStatus.READY, DocumentStatus.DELETING}:
            return False
        document.status = status
        document.error_message = error_message[:512]
        return True

    @staticmethod
    async def recover_stale_indexes(
        *,
        db: AsyncSession,
        stale_before: datetime,
        limit: int,
    ) -> list[tuple[int, int]]:
        """把长时间无进展的索引任务恢复为待处理状态。"""
        documents = await document_dao.get_stale_index_documents(db, stale_before=stale_before, limit=limit)
        recovered_time = timezone.now()
        for document in documents:
            document.status = DocumentStatus.PENDING
            document.error_message = '索引任务超时，已重新排队'
            document.updated_time = recovered_time
        return [(document.id, document.index_version) for document in documents]

    @staticmethod
    async def get_deleting_document_ids(*, db: AsyncSession) -> list[int]:
        """获取仍待补偿删除的文档 ID。"""
        return await document_dao.get_ids_by_status(db, status=DocumentStatus.DELETING)

    @staticmethod
    async def get(
        *, db: AsyncSession, knowledge_base_id: int, pk: int, user_id: int, is_admin: bool, write: bool = False
    ) -> Document:
        await knowledge_base_service.get(db=db, pk=knowledge_base_id, user_id=user_id, is_admin=is_admin, write=write)
        data = await document_dao.get_in_kb(db, pk=pk, knowledge_base_id=knowledge_base_id)
        if not data:
            raise errors.NotFoundError(msg='文档不存在')
        return data

    @staticmethod
    async def get_list(*, db: AsyncSession, knowledge_base_id: int, user_id: int, is_admin: bool) -> list[Document]:
        await knowledge_base_service.get(db=db, pk=knowledge_base_id, user_id=user_id, is_admin=is_admin)
        return await document_dao.get_list(db, knowledge_base_id=knowledge_base_id)

    @staticmethod
    async def get_chunks(
        *, db: AsyncSession, knowledge_base_id: int, pk: int, user_id: int, is_admin: bool
    ) -> list[Chunk]:
        await DocumentService.get(db=db, knowledge_base_id=knowledge_base_id, pk=pk, user_id=user_id, is_admin=is_admin)
        return await chunk_dao.get_list(db, document_id=pk)

    @staticmethod
    async def retry(*, db: AsyncSession, knowledge_base_id: int, pk: int, user_id: int, is_admin: bool) -> Document:
        data = await DocumentService.get(
            db=db, knowledge_base_id=knowledge_base_id, pk=pk, user_id=user_id, is_admin=is_admin, write=True
        )
        data.status = DocumentStatus.PENDING
        data.error_message = None
        data.index_version += 1
        profile = await get_or_create_index_profile(db=db)
        data.index_profile_id = profile.id
        await enqueue_document_index(db=db, document_id=data.id, index_version=data.index_version)
        return data

    @staticmethod
    async def delete(*, db: AsyncSession, knowledge_base_id: int, pk: int, user_id: int, is_admin: bool) -> None:
        data = await DocumentService.get(
            db=db, knowledge_base_id=knowledge_base_id, pk=pk, user_id=user_id, is_admin=is_admin, write=True
        )
        data.status = DocumentStatus.DELETING
        await enqueue_document_delete(db=db, document_id=data.id)


document_service = DocumentService()
