from fastapi import APIRouter

from backend.app.rag.api.v1.document import router as document_router
from backend.app.rag.api.v1.knowledge_base import router as knowledge_base_router
from backend.app.rag.api.v1.query import router as query_router
from backend.core.conf import settings

v1 = APIRouter(prefix=settings.FASTAPI_API_V1_PATH)
v1.include_router(knowledge_base_router)
v1.include_router(document_router)
v1.include_router(query_router)
