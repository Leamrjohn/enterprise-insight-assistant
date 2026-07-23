import logging
import time
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core.logging import request_id_context


logger = logging.getLogger("app.request")

# ── 限流 ──────────────────────────────────
_rate_limit_store: dict[str, list[float]] = {}
RATE_LIMIT_MAX = 100        # 每分钟最多 100 次请求
RATE_LIMIT_WINDOW = 60      # 滑动窗口 60 秒


def _check_rate_limit(api_key: str) -> JSONResponse | None:
    """检查 API Key 是否超过频率限制。超限返回 429，未超限返回 None。"""
    if not api_key:
        return None

    now = time.time()
    timestamps = _rate_limit_store.get(api_key)

    if timestamps is None:
        _rate_limit_store[api_key] = [now]
        return None

    # 清理过期的时间戳（超过 60 秒的）
    cutoff = now - RATE_LIMIT_WINDOW
    timestamps[:] = [ts for ts in timestamps if ts > cutoff]

    if len(timestamps) >= RATE_LIMIT_MAX:
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后重试"},
        )

    timestamps.append(now)
    return None


async def request_context_middleware(
    request: Request,
    call_next,
) -> Response:
    incoming_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        incoming_request_id if 0 < len(incoming_request_id) <= 128 else uuid4().hex
    )
    token = request_id_context.set(request_id)
    request.state.request_id = request_id

    # ── 限流检查 ──────────────────────────────
    api_key = request.headers.get("X-API-Key", "")
    rate_limit_response = _check_rate_limit(api_key)
    if rate_limit_response is not None:
        return rate_limit_response

    start_time = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )
        logger.exception(
            "Unhandled request error",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            },
        )
        raise
    else:
        duration_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
    finally:
        request_id_context.reset(token)
