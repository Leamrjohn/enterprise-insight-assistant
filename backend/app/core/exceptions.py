from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError


class RetrievalError(RuntimeError):
    """RAG 检索过程失败。"""


class EmbeddingError(RetrievalError):
    """生成查询向量失败。"""


class VectorSearchError(RetrievalError):
    """向量数据库检索失败。"""


class RerankingError(RetrievalError):
    """候选文档重排失败。"""


class RetryableModelError(Exception):
    pass


class PermanentModelError(Exception):
    pass


class StructuredOutputError(ValueError):
    """模型输出无法解析为约定的结构化结果。"""


class DocumentUploadError(Exception):
    pass


class EmptyDocumentError(DocumentUploadError):
    pass


class UnsupportedDocumentTypeError(DocumentUploadError):
    pass


class DocumentTooLargeError(DocumentUploadError):
    pass


class InvalidDocumentNameError(DocumentUploadError):
    pass


class DuplicateDocumentError(DocumentUploadError):
    pass


class DuplicateLabelError(Exception):
    pass


class DuplicatePromptTemplateError(Exception):
    pass


class TaskCannotBeCancelledError(Exception):
    pass


async def unhandled_exception_handler(
    request: Request,
    _exc: Exception,
) -> JSONResponse:
    request_id = getattr(
        request.state,
        "request_id",
        uuid4().hex,
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "message": "internal server error",
            "details": [],
        },
        headers={"X-Request-ID": request_id},
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    request_id = getattr(
        request.state,
        "request_id",
        uuid4().hex,
    )
    code_by_status = {
        404: "not_found",
        503: "service_unavailable",
    }
    headers = dict(exc.headers or {})
    headers["X-Request-ID"] = request_id

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code_by_status.get(exc.status_code, "http_error"),
            "message": str(exc.detail),
            "details": [],
        },
        headers=headers,
    )


async def request_validation_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    request_id = getattr(
        request.state,
        "request_id",
        uuid4().hex,
    )
    details = [
        {"type": err["type"], "loc": err["loc"], "msg": err["msg"]}
        for err in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "request validation failed",
            "details": details,
        },
        headers={"X-Request-ID": request_id},
    )
