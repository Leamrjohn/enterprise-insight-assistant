from fastapi import APIRouter
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.document import router as document_router
from app.api.auth import router as auth_router
from app.api.tasks import router as tasks_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(health_router)
router.include_router(document_router)
router.include_router(auth_router)
router.include_router(tasks_router)
