from app.core.gateway.deepseek import DeepSeekGateway
from app.core.gateway.factory import get_model_gateway
from app.core.gateway.local import LocalModelGateway
from app.core.settings import get_settings


def test_gateway_factory_returns_deepseek_gateway(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-flash")

    get_settings.cache_clear()
    get_model_gateway.cache_clear()
    try:
        gateway = get_model_gateway()
        assert isinstance(gateway, DeepSeekGateway)
    finally:
        get_model_gateway.cache_clear()
        get_settings.cache_clear()


def test_gateway_factory_returns_local_gateway(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")

    get_settings.cache_clear()
    get_model_gateway.cache_clear()
    try:
        gateway = get_model_gateway()
        assert isinstance(gateway, LocalModelGateway)
    finally:
        get_model_gateway.cache_clear()
        get_settings.cache_clear()
