import time
from logging import getLogger
from app.core.settings import get_settings
from openai import OpenAI
from app.core.gateway.base import ModelGateway, ModelCallRecord
from tiktoken import encoding_for_model, get_encoding


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
from app.core.exceptions import PermanentModelError, RetryableModelError


class DeepSeekGateway(ModelGateway):
    def __init__(self, model_name: str | None = None):
        settings = get_settings()
        api_key = settings.deepseek_api_key
        if api_key is None or not api_key.get_secret_value():
            raise PermanentModelError(
                "DEEPSEEK_API_KEY environment variable is not configured"
            )
        self.client = OpenAI(
            api_key=api_key.get_secret_value(),
            base_url=settings.deepseek_base_url,
            max_retries=0,
        )
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
        create_at = time.perf_counter()
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

            duration_ms = (time.perf_counter() - create_at) * 1000
            record = ModelCallRecord(
                model_name=self.model_name,
                prompt=prompt,
                response=result,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=0.0,
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
            return result
        except (
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
        ) as exc:
            # 保留原有失败日志记录代码
            self._log_failure(prompt=prompt, create_at=create_at, exc=exc)
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
            raise PermanentModelError("Model request configuration is invalid") from exc

        except Exception as exc:
            self._log_failure(prompt=prompt, create_at=create_at, exc=exc)
            raise

    def count_tokens(self, text: str) -> int:
        try:
            encoding = encoding_for_model(self.model_name)
        except KeyError:
            encoding = get_encoding("o200k_base")
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
