from fastapi import APIRouter

from backend.app.admin.api.v1.log.login_log import router as login_log_router
from backend.app.admin.api.v1.log.opera_log import router as opera_log_router

router = APIRouter(prefix='/logs')

router.include_router(login_log_router, prefix='/login', tags=['登录日志'])
router.include_router(opera_log_router, prefix='/opera', tags=['操作日志'])
