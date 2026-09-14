from fastapi import APIRouter
from app.modules.observability.health_api import router as health_router
from app.modules.documents.api import router as document_router
from app.modules.identity.api import router as auth_router
from app.modules.conversations.api import router as conversations_router
from app.modules.organizations.api import router as companies_router
from app.modules.reviews.api import router as review_requests_router
from app.modules.observability.api import router as observability_router
from app.modules.input_artifacts.api import router as input_artifacts_router

router = APIRouter()
router.include_router(health_router)
router.include_router(document_router)
router.include_router(auth_router)
router.include_router(conversations_router)
router.include_router(companies_router)
router.include_router(review_requests_router)
router.include_router(observability_router)
router.include_router(input_artifacts_router)
