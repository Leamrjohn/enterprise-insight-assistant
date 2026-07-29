import time
from logging import getLogger
from app.core.settings import get_settings
from openai import OpenAI
from tiktoken import encoding_for_model
from app.core.gateway.base import ModelGateway, ModelCallRecord
from app.core.exceptions import PermanentModelError, RetryableModelError
from app.services.model_governance import (
    fallback_chain_scope,
    next_fallback_model,
    record_model_call,
    reserve_model_call,
)
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)


class OpenAIGateway(ModelGateway):
    def __init__(self, model_name: str | None = None):
        settings = get_settings()
        api_key = settings.openai_api_key
        if api_key is None or not api_key.get_secret_value():
            raise PermanentModelError(
                "OPENAI_API_KEY environment variable is not configured"
            )
        self.client = OpenAI(api_key=api_key.get_secret_value(), max_retries=0)
        self.model_name = model_name or settings.llm_model
        self.timeout_seconds = settings.llm_timeout_seconds
        self.temperature = settings.llm_temperature
        self.max_output_tokens = settings.llm_max_output_tokens
        self.logger = getLogger(__name__)

    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        json_mode: bool = False,
    ) -> str:
        with fallback_chain_scope(self.model_name):
            return self._chat_once(prompt, system_prompt, json_mode=json_mode)

    def _chat_once(
        self, prompt: str, system_prompt: str | None = None, *, json_mode: bool = False
    ) -> str:
        create_at = time.perf_counter()
        governance_scope = reserve_model_call(
            provider="openai",
            model_name=self.model_name,
            estimated_prompt_tokens=self.count_tokens(prompt),
        )
        try:
            messages = []
            if system_prompt is not None:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            request_kwargs = {
                "model": self.model_name,
                "messages": messages,
                "timeout": self.timeout_seconds,
                "temperature": self.temperature,
                "max_tokens": self.max_output_tokens,
            }
            if json_mode:
                request_kwargs["response_format"] = {"type": "json_object"}
            response = self.client.chat.completions.create(**request_kwargs)

            result = response.choices[0].message.content
            if result is None or not result.strip():
                if json_mode:
                    raise RetryableModelError("Model returned an empty JSON response")
                result = ""
            usage = response.usage
            if usage is not None:
                prompt_tokens = usage.prompt_tokens
                completion_tokens = usage.completion_tokens
            else:
                prompt_tokens = 0
                completion_tokens = 0
            prompt_price = 0.03
            completion_price = 0.06
            cost = (
                prompt_tokens / 1000 * prompt_price
                + completion_tokens / 1000 * completion_price
            )
            duration_ms = (time.perf_counter() - create_at) * 1000
            record = ModelCallRecord(
                model_name=self.model_name,
                prompt=prompt,
                response=result,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=cost,
                duration_ms=round(duration_ms, 2),
            )
            self.logger.info(
                "Model call completed",
                extra={
                    "model": record.model_name,
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                    "duration_ms": record.duration_ms,
                    "cost": record.cost,
                },
            )
            record_model_call(
                governance_scope,
                provider="openai",
                model_name=self.model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=cost,
                duration_ms=duration_ms,
                result_category="success",
            )
            return result
        except (
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
        ) as exc:
            # 保留原有失败日志记录代码
            self._log_failure(prompt=prompt, create_at=create_at, exc=exc)
            record_model_call(
                governance_scope,
                provider="openai",
                model_name=self.model_name,
                duration_ms=(time.perf_counter() - create_at) * 1000,
                result_category="retryable_error",
                error_code="provider_temporary_error",
            )
            fallback_model = next_fallback_model(self.model_name)
            if fallback_model is not None:
                failed_model = self.model_name
                self.model_name = fallback_model
                try:
                    return self._chat_once(prompt, system_prompt, json_mode=json_mode)
                finally:
                    self.model_name = failed_model
            raise RetryableModelError(
                "Model service is temporarily unavailable"
            ) from exc

        except (
            AuthenticationError,
            PermissionDeniedError,
            BadRequestError,
            NotFoundError,
            UnprocessableEntityError,
        ) as exc:
            # 保留原有失败日志记录代码
            self._log_failure(prompt=prompt, create_at=create_at, exc=exc)
            record_model_call(
                governance_scope,
                provider="openai",
                model_name=self.model_name,
                duration_ms=(time.perf_counter() - create_at) * 1000,
                result_category="permanent_error",
                error_code="provider_request_invalid",
            )
            raise PermanentModelError("Model request configuration is invalid") from exc

        except Exception as exc:
            self._log_failure(prompt=prompt, create_at=create_at, exc=exc)
            record_model_call(
                governance_scope,
                provider="openai",
                model_name=self.model_name,
                duration_ms=(time.perf_counter() - create_at) * 1000,
                result_category="unexpected_error",
                error_code="provider_unexpected_error",
            )
            raise

    def count_tokens(self, text: str) -> int:
        encoding = encoding_for_model(self.model_name)
        return len(encoding.encode(text))

    def _log_failure(
        self,
        *,
        prompt: str,
        create_at: float,
        exc: Exception,
    ) -> None:
        duration_ms = (time.perf_counter() - create_at) * 1000
        record = ModelCallRecord(
            model_name=self.model_name,
            prompt=prompt,
            response=None,
            success=False,
            error_message=str(exc),
            duration_ms=round(duration_ms, 2),
        )
        self.logger.error(
            "Model call failed",
            extra={
                "model": record.model_name,
                "error": record.error_message,
                "duration_ms": record.duration_ms,
                "error_type": type(exc).__name__,
            },
        )
