"""错误处理与重试 —— 异常分类 + 指数退避重试"""

import logging
import random
import time

logger = logging.getLogger(__name__)

_failure_count = 0
_last_failure_time = 0.0
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN = 30


def classify_exception(exc: Exception) -> str:
    """判断异常是可重试的还是永久性的"""
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return "retryable"
    if isinstance(exc, (ValueError, TypeError, KeyError, PermissionError)):
        return "permanent"
    return "permanent"


def _record_failure():
    global _failure_count, _last_failure_time
    _failure_count += 1
    _last_failure_time = time.time()


def _record_success():
    global _failure_count
    _failure_count = 0


def retry_with_backoff(func, max_retries=3, base_delay=1.0):
    """
    指数退避重试。

    func: 可能失败的函数（无参数）
    max_retries: 最大重试次数
    base_delay: 基础等待秒数

    重试延迟: base_delay × 2^attempt + 随机抖动
    """
    _check_circuit_breaker()

    last_exc = None
    for attempt in range(max_retries):
        try:
            result = func()
            _record_success()
            return result
        except Exception as exc:
            _record_failure()
            last_exc = exc
            category = classify_exception(exc)
            if category == "permanent":
                logger.error("永久性错误，放弃重试: %s", exc)
                raise
            jitter = random.uniform(-0.1, 0.1) * base_delay
            delay = base_delay * (2**attempt) + jitter
            logger.warning(
                "第%d次重试失败，%d秒后重试: %s",
                attempt + 1,
                int(delay),
                exc,
            )
            time.sleep(delay)
    logger.error("重试%d次全部失败: %s", max_retries, last_exc)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retry_with_backoff 失败但无异常信息")


def _check_circuit_breaker():
    """检查是否在熔断状态"""
    global _failure_count
    if _failure_count >= CIRCUIT_BREAKER_THRESHOLD:
        elapsed = time.time() - _last_failure_time
        if elapsed < CIRCUIT_BREAKER_COOLDOWN:
            remaining = int(CIRCUIT_BREAKER_COOLDOWN - elapsed)
            raise RuntimeError(f"熔断中，请 {remaining} 秒后重试")
        _failure_count = 0
