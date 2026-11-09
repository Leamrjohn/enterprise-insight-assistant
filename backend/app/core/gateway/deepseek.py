import json
import time
from logging import getLogger
from typing import cast

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from app.core.exceptions import (
    MalformedModelResponseError,
    PermanentModelError,
    RetryableModelError,
)
from app.core.gateway.base import (
    ModelCallRecord,
    ModelGateway,
    ToolCall,
    ToolChatResponse,
)
from app.core.settings import get_settings
from app.core.tokenizer import count_tokens
from app.modules.runtime.model_governance import (
    estimate_chat_prompt_tokens,
    fallback_chain_scope,
    frozen_max_output_tokens,
    frozen_timeout_seconds,
    next_fallback_model,
    prompt_provenance,
    record_model_call,
    reserve_model_call,
)


def _response_details(response, usage) -> dict:
    """What the provider says beyond tokens: was it cut off, who answered, cache use."""
    details = {
        "finish_reason": getattr(response.choices[0], "finish_reason", None),
        "served_model": getattr(response, "model", None),
        "prompt_cache_hit_tokens": getattr(usage, "prompt_cache_hit_tokens", None),
        "prompt_cache_miss_tokens": getattr(usage, "prompt_cache_miss_tokens", None),
    }
    return {
        key: value for key, value in details.items() if isinstance(value, (str, int))
    }


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
        with fallback_chain_scope(self.model_name):
            # Without tools _chat_once returns the text.
            return cast(
                str, self._chat_once(prompt, system_prompt, json_mode=json_mode)
            )

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        tool_choice: str | dict = "auto",
    ) -> ToolChatResponse:
        # The whole request is the "prompt" for the ledger's estimate and hash.
        prompt = json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False)
        with fallback_chain_scope(self.model_name):
            # With tools _chat_once returns the structured response.
            return cast(
                ToolChatResponse,
                self._chat_once(
                    prompt,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                ),
            )

    def _chat_once(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        json_mode: bool = False,
        messages: list[dict] | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
    ) -> str | ToolChatResponse:
        create_at = time.perf_counter()
        max_output_tokens = frozen_max_output_tokens(self.max_output_tokens)
        timeout_seconds = frozen_timeout_seconds(self.timeout_seconds)
        provenance = prompt_provenance(
            prompt,
            system_prompt,
            json_mode=json_mode,
            timeout_seconds=timeout_seconds,
            temperature=self.temperature,
            max_output_tokens=max_output_tokens,
        )
        governance_scope = reserve_model_call(
            provider="deepseek",
            model_name=self.model_name,
            estimated_prompt_tokens=estimate_chat_prompt_tokens(
                self.count_tokens, prompt, system_prompt
            ),
            reserved_completion_tokens=max_output_tokens,
            pricing_parameters=provenance["model_parameters"],
        )
        try:
            if messages is None:
                request_messages = []
                if system_prompt is not None:
                    request_messages.append(
                        {"role": "system", "content": system_prompt}
                    )
                request_messages.append({"role": "user", "content": prompt})
            else:
                request_messages = messages
            request_kwargs = {
                "model": self.model_name,
                "messages": request_messages,
                "timeout": timeout_seconds,
                "temperature": self.temperature,
                "max_tokens": max_output_tokens,
            }
            if json_mode:
                request_kwargs["response_format"] = {"type": "json_object"}
                # Structured internal contracts need parsed content, not a
                # reasoning trace. DeepSeek documents this request option for
                # turning off thinking mode.
                request_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            if tools is not None:
                request_kwargs["tools"] = tools
                request_kwargs["tool_choice"] = tool_choice
                request_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            response = self.client.chat.completions.create(**request_kwargs)

            try:
                result = response.choices[0].message.content
                usage = response.usage
                tool_calls = (
                    tuple(
                        ToolCall(
                            id=call.id,
                            name=call.function.name,
                            arguments=call.function.arguments,
                        )
                        for call in (response.choices[0].message.tool_calls or [])
                    )
                    if tools is not None
                    else ()
                )
            except (AttributeError, IndexError, TypeError) as exc:
                raise MalformedModelResponseError(
                    "Model returned a malformed response"
                ) from exc
            if result is None or not result.strip():
                if json_mode or (tools is not None and not tool_calls):
                    raise RetryableModelError("Model returned an empty JSON response")
                result = ""
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
                cost=None,
                duration_ms=round(duration_ms, 2),
            )
            self.logger.info(
                "Model call completed",
                extra={
                    "model": record.model_name,
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                    "duration_ms": record.duration_ms,
                    "cost_status": "settled_by_ledger",
                },
            )
            response_details = _response_details(response, usage)
            if response_details.get("finish_reason") == "length":
                self.logger.warning(
                    "Model output reached the output token limit",
                    extra={
                        "model": record.model_name,
                        "completion_tokens": record.completion_tokens,
                    },
                )
            record_model_call(
                governance_scope,
                provider="deepseek",
                model_name=self.model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ms=duration_ms,
                result_category="success",
                resource_usage=response_details,
                **provenance,
            )
            if tools is not None:
                return ToolChatResponse(text=result or None, tool_calls=tool_calls)
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
                provider="deepseek",
                model_name=self.model_name,
                duration_ms=(time.perf_counter() - create_at) * 1000,
                result_category="retryable_error",
                error_code="provider_temporary_error",
                **provenance,
            )
            fallback_model = next_fallback_model(self.model_name)
            if fallback_model is not None:
                failed_model = self.model_name
                self.model_name = fallback_model
                try:
                    return self._chat_once(
                        prompt,
                        system_prompt,
                        json_mode=json_mode,
                        messages=messages,
                        tools=tools,
                        tool_choice=tool_choice,
                    )
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
                provider="deepseek",
                model_name=self.model_name,
                duration_ms=(time.perf_counter() - create_at) * 1000,
                result_category="permanent_error",
                error_code="provider_request_invalid",
                **provenance,
            )
            raise PermanentModelError("Model request configuration is invalid") from exc

        except RetryableModelError as exc:
            # An empty JSON response is a retryable provider-output failure,
            # not an unexpected local exception.  Preserve the reserved prompt
            # estimate in the ledger and let the caller apply its bounded retry.
            self._log_failure(prompt=prompt, create_at=create_at, exc=exc)
            record_model_call(
                governance_scope,
                provider="deepseek",
                model_name=self.model_name,
                duration_ms=(time.perf_counter() - create_at) * 1000,
                result_category="retryable_error",
                error_code=(
                    "provider_malformed_response"
                    if isinstance(exc, MalformedModelResponseError)
                    else "provider_empty_json_response"
                ),
                **provenance,
            )
            raise

        except Exception as exc:
            self._log_failure(prompt=prompt, create_at=create_at, exc=exc)
            record_model_call(
                governance_scope,
                provider="deepseek",
                model_name=self.model_name,
                duration_ms=(time.perf_counter() - create_at) * 1000,
                result_category="unexpected_error",
                error_code="provider_unexpected_error",
                **provenance,
            )
            raise

    def count_tokens(self, text: str) -> int:
        return count_tokens(text, model_name=self.model_name)

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
            "Model call failed (%s)",
            type(exc).__name__,
            extra={
                "model": record.model_name,
                "error": record.error_message,
                "duration_ms": record.duration_ms,
                "error_type": type(exc).__name__,
            },
        )
