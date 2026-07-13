import time
from logging import getLogger
import os
from openai import OpenAI
from tiktoken import encoding_for_model
from app.core.gateway.base import ModelGateway, ModelCallRecord


class OpenAIGateway(ModelGateway):
    def __init__(self, model_name: str | None = None):
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key is None:
            raise ValueError("OPENAI_API_KEY环境变量未配置")
        self.client = OpenAI(api_key=api_key, max_retries=3)
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4")
        self.logger = getLogger(__name__)

    def chat(self, prompt: str, system_prompt: str | None = None) -> str:
        create_at = time.perf_counter()
        try:
            messages = []
            if system_prompt is not None:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                timeout=30,
                temperature=0.7,
                max_tokens=1024,
            )

            result = response.choices[0].message.content
            if result is None:
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
            cost = prompt_tokens / 1000 * prompt_price + completion_tokens / 1000 * completion_price
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
            self.logger.info("Model call completed", extra={
                "model": record.model_name,
                "prompt_tokens": record.prompt_tokens,
                "completion_tokens": record.completion_tokens,
                "duration_ms": record.duration_ms,
                "cost": record.cost,
            })
            return result
        except Exception as exc:
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
                },
            )
            raise

    def count_tokens(self, text: str) -> int:
        encoding = encoding_for_model(self.model_name)
        return len(encoding.encode(text))
