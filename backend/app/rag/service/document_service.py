import hashlib

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rag.chunking import contextualize_chunk, split_text
from backend.app.rag.crud.crud_rag import chunk_dao, document_dao
from backend.app.rag.enums import DocumentStatus
from backend.app.rag.model import Chunk, Document
from backend.app.rag.service.knowledge_base_service import knowledge_base_service
from backend.app.rag.adapters.embedding import embedding_provider
from backend.app.rag.adapters.storage import storage
from backend.common.exception import errors
from backend.core.conf import settings


class DocumentService:
    @staticmethod
    async def create(*, db: AsyncSession, knowledge_base_id: int, user_id: int, is_admin: bool, filename: str, content: bytes, mime_type: str | None) -> Document:
        kb = await knowledge_base_service.get(db=db, pk=knowledge_base_id, user_id=user_id, is_admin=is_admin, write=True)
        suffix = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if suffix not in {'txt', 'md', 'docx'}:
            raise errors.RequestError(msg='仅支持 .txt、.md、.docx 文件')
        if len(content) > settings.RAG_MAX_FILE_SIZE:
            raise errors.RequestError(msg=f'文件不能超过 {settings.RAG_MAX_FILE_SIZE // 1024 // 1024}MB')
        digest = hashlib.sha256(content).hexdigest()
        storage_key = f'{kb.id}/{digest}.{suffix}'
        storage.put(key=storage_key, content=content)
        data = Document(knowledge_base_id=kb.id, filename=filename, file_type=suffix, mime_type=mime_type, storage_key=storage_key, file_size=len(content), content_hash=digest)
        db.add(data)
        await db.flush()
        from backend.app.task.tasks.rag.tasks import index_document

        index_document.delay(data.id)
        return data

    @staticmethod
    async def index_content(*, db: AsyncSession, document: Document, content: bytes) -> None:
        from backend.app.rag.parsers.text import parse_document

        document.status = DocumentStatus.PROCESSING
        try:
            text = parse_document(filename=document.filename, data=content)
            pieces = split_text(text, chunk_size=settings.RAG_CHUNK_SIZE, overlap=settings.RAG_CHUNK_OVERLAP)
            if not pieces:
                raise ValueError('文档没有可索引正文')
            vectors = await embedding_provider.embed([contextualize_chunk(filename=document.filename, heading_path=[], content=item) for item in pieces])
            await db.execute(delete(Chunk).where(Chunk.document_id == document.id))
            for index, (piece, vector) in enumerate(zip(pieces, vectors, strict=True)):
                db.add(Chunk(knowledge_base_id=document.knowledge_base_id, document_id=document.id, chunk_index=index, content=piece, contextual_content=contextualize_chunk(filename=document.filename, heading_path=[], content=piece), search_text=piece, content_hash=hashlib.sha256(piece.encode()).hexdigest(), char_count=len(piece), token_count=max(len(piece) // 4, 1), embedding=vector, index_version=document.index_version))
            document.parsed_content = text
            document.chunk_count = len(pieces)
            document.status = DocumentStatus.READY
        except Exception as exc:
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)[:512]

    @staticmethod
    async def get(*, db: AsyncSession, knowledge_base_id: int, pk: int, user_id: int, is_admin: bool) -> Document:
        await knowledge_base_service.get(db=db, pk=knowledge_base_id, user_id=user_id, is_admin=is_admin)
        data = await document_dao.get_in_kb(db, pk=pk, knowledge_base_id=knowledge_base_id)
        if not data:
            raise errors.NotFoundError(msg='文档不存在')
        return data

    @staticmethod
    async def get_list(*, db: AsyncSession, knowledge_base_id: int, user_id: int, is_admin: bool) -> list[Document]:
        await knowledge_base_service.get(db=db, pk=knowledge_base_id, user_id=user_id, is_admin=is_admin)
        return await document_dao.get_list(db, knowledge_base_id=knowledge_base_id)

    @staticmethod
    async def get_chunks(*, db: AsyncSession, knowledge_base_id: int, pk: int, user_id: int, is_admin: bool) -> list[Chunk]:
        await DocumentService.get(db=db, knowledge_base_id=knowledge_base_id, pk=pk, user_id=user_id, is_admin=is_admin)
        return await chunk_dao.get_list(db, document_id=pk)

    @staticmethod
    async def retry(*, db: AsyncSession, knowledge_base_id: int, pk: int, user_id: int, is_admin: bool) -> Document:
        data = await DocumentService.get(db=db, knowledge_base_id=knowledge_base_id, pk=pk, user_id=user_id, is_admin=is_admin)
        data.status = DocumentStatus.PENDING
        data.error_message = None
        from backend.app.task.tasks.rag.tasks import index_document

        index_document.delay(data.id)
        return data

    @staticmethod
    async def delete(*, db: AsyncSession, knowledge_base_id: int, pk: int, user_id: int, is_admin: bool) -> None:
        data = await DocumentService.get(db=db, knowledge_base_id=knowledge_base_id, pk=pk, user_id=user_id, is_admin=is_admin)
        data.deleted = data.id
        storage.delete(key=data.storage_key)


document_service = DocumentService()
