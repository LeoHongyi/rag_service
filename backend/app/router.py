from fastapi import APIRouter

from backend.app.admin.api.router import v1 as admin_v1
from backend.app.task.api.router import v1 as task_v1
from backend.app.rag.api.router import v1 as rag_v1

router = APIRouter()

router.include_router(admin_v1)
router.include_router(task_v1)
router.include_router(rag_v1)
