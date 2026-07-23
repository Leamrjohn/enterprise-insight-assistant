from functools import lru_cache

from app.core.gateway.base import ModelGateway
from app.core.gateway.local import LocalModelGateway
from app.core.gateway.openai import OpenAIGateway
from app.core.settings import get_settings
from app.core.gateway.deepseek import DeepSeekGateway


@lru_cache
def get_model_gateway() -> ModelGateway:
    settings = get_settings()

    if settings.llm_provider == "local":
        return LocalModelGateway()
    if settings.llm_provider == "openai":
        return OpenAIGateway()
    if settings.llm_provider == "deepseek":
        return DeepSeekGateway()

    raise RuntimeError(f"Unsupported LLM provider : {settings.llm_provider}")
