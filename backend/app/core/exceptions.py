from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError


_CHINESE_ERROR_MESSAGES = {
    "invalid or missing API key": "API Key 无效或未提供。",
    "account is inactive": "当前账户已被禁用。",
    "company membership is not approved": "当前公司的成员资格尚未获批准。",
    "company membership is invalid": "当前公司的成员资格无效。",
    "administrator permission required": "此操作需要管理员权限。",
    "analysis permission required": "当前用户没有发起经营分析的权限。",
    "company or data source not found": "当前公司中未找到该数据源。",
    "data source not found": "未找到数据源。",
    "schema snapshot not found": "未找到契约快照。",
    "conversation not found": "未找到会话。",
    "task not found": "未找到分析任务。",
    "member not found": "未找到公司成员。",
    "document not found": "未找到文档。",
    "membership application not found": "未找到成员申请。",
    "account already belongs to a company": "该账户已经加入了一家公司。",
    "cannot change the last owner": "不能修改公司最后一位所有者。",
    "invalid application status": "成员申请状态无效。",
    "request validation failed": "请求参数校验失败。",
    "internal server error": "服务器内部错误，请稍后重试。",
    "service unavailable": "服务暂时不可用，请稍后重试。",
    "platform already has a company": "系统已完成首次初始化，不能再次创建初始管理员。",
    "该账户已设置密码登录": "该账户已设置密码登录。",
    "account already has an application": "该账户已有成员申请。",
}

_VALIDATION_MESSAGES = {
    "missing": "此字段为必填项。",
    "string_too_short": "输入内容长度不足。",
    "string_too_long": "输入内容长度超出限制。",
    "string_pattern_mismatch": "输入格式不符合要求。",
    "int_parsing": "请输入有效的整数。",
    "greater_than": "输入值必须大于允许的最小值。",
    "greater_than_equal": "输入值小于允许的最小值。",
    "less_than": "输入值必须小于允许的最大值。",
    "less_than_equal": "输入值超过允许的最大值。",
    "json_invalid": "请求内容不是有效的 JSON。",
}


def localize_error_message(message: str) -> str:
    """Return a safe Chinese message without exposing backend implementation text."""
    return _CHINESE_ERROR_MESSAGES.get(message, message)


def localize_validation_error(error_type: str) -> str:
    return _VALIDATION_MESSAGES.get(error_type, "请求参数不符合要求。")


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
            "message": "服务器内部错误，请稍后重试。",
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
            "message": localize_error_message(str(exc.detail)),
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
        {
            "type": err["type"],
            "loc": err["loc"],
            "msg": localize_validation_error(err["type"]),
        }
        for err in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "请求参数校验失败。",
            "details": details,
        },
        headers={"X-Request-ID": request_id},
    )
