from fastapi import APIRouter
from app.api.health import router as health_router
from app.api.document import router as document_router
from app.api.auth import router as auth_router
from app.api.todo_items import router as todo_items_router
from app.api.labels import router as label_router
from app.api.prompt_templates import router as prompt_template_router
from app.api.conversations import router as conversations_router
from app.api.companies import router as companies_router
from app.api.review_requests import router as review_requests_router
from app.api.observability import router as observability_router

router = APIRouter()
router.include_router(health_router)
router.include_router(document_router)
router.include_router(auth_router)
router.include_router(todo_items_router)
router.include_router(label_router)
router.include_router(prompt_template_router)
router.include_router(conversations_router)
router.include_router(companies_router)
router.include_router(review_requests_router)
router.include_router(observability_router)
