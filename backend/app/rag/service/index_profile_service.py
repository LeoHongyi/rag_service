import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.rag.model import IndexProfile
from backend.core.conf import settings


def build_index_profile_payload() -> dict[str, int | str | None]:
    """构造当前索引链路的可序列化配置快照。"""
    return {
        'parser_name': 'rag.text.parse_document',
        'parser_version': '2',
        'chunker_name': 'rag.chunking.split_text',
        'chunker_version': '1',
        'chunk_size': settings.RAG_CHUNK_SIZE,
        'chunk_overlap': settings.RAG_CHUNK_OVERLAP,
        'tokenizer_name': 'character_estimate',
        'tokenizer_version': '1',
        'embedding_model': settings.RAG_EMBEDDING_MODEL,
        'embedding_dimensions': settings.RAG_EMBEDDING_DIMENSIONS,
        'embedding_instruction': None,
        'lexical_config': 'postgresql-simple',
    }


async def get_or_create_index_profile(*, db: AsyncSession) -> IndexProfile:
    """获取当前配置对应的不可变索引快照。"""
    payload = build_index_profile_payload()
    profile_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    profile = await db.scalar(select(IndexProfile).where(IndexProfile.profile_hash == profile_hash))
    if profile:
        return profile
    profile = IndexProfile(profile_hash=profile_hash, **payload)
    db.add(profile)
    await db.flush()
    return profile
