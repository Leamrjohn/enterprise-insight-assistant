import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import router
from app.core.exceptions import (
    http_exception_handler,
    request_validation_handler,
    unhandled_exception_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import request_context_middleware
from app.core.settings import get_settings
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    for directory in (
        settings.upload_dir,
        settings.knowledge_dir,
        settings.faiss_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    logger.info(
        "Application started",
        extra={"path": str(settings.storage_dir)},
    )
    yield
    engine.dispose()
    logger.info("Application stopped")


settings = get_settings()
configure_logging(settings)

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_context_middleware)
app.add_exception_handler(
    StarletteHTTPException,
    http_exception_handler,  # type: ignore[arg-type]
)
app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(router)
