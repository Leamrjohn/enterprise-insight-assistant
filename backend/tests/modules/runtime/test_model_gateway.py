"""测试 Model Gateway"""

import pytest
from httpx import Request, Response
from openai import APITimeoutError, AuthenticationError
from app.core.gateway.local import LocalModelGateway
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.gateway.deepseek import DeepSeekGateway
from app.core.settings import get_settings
from app.modules.runtime.model_governance import model_call_scope


def test_local_gateway_returns_string():
    """测试 chat 方法返回字符串"""
    gateway = LocalModelGateway()
    result = gateway.chat("测试问题")
    assert isinstance(result, str)
    assert len(result) > 0
    assert "测试问题" in result


def test_local_gateway_tokens():
    """测试 count_tokens 估算"""
    gateway = LocalModelGateway()
    tokens = gateway.count_tokens("hello world")
    assert tokens == 22  # len("hello world") * 2 = 22
    assert isinstance(tokens, int)


def test_deepseek_gateway_sends_expected_request(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "5")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.1")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "16")

    get_settings.cache_clear()
    try:
        gateway = DeepSeekGateway()

        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="模拟回答"),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )
        create = Mock(return_value=response)
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create),
            )
        )

        monkeypatch.setattr(gateway, "client", fake_client)

        result = gateway.chat("用户问题", system_prompt="系统规则")

        assert result == "模拟回答"
        create.assert_called_once_with(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": "系统规则"},
                {"role": "user", "content": "用户问题"},
            ],
            timeout=5,
            temperature=0.1,
            max_tokens=16,
        )
    finally:
        get_settings.cache_clear()


def test_deepseek_gateway_requests_json_mode(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        gateway = DeepSeekGateway()
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content='{"answer":"ok"}'))
            ],
            usage=None,
        )
        create = Mock(return_value=response)
        gateway.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )

        assert gateway.chat("prompt", json_mode=True) == '{"answer":"ok"}'
        assert create.call_args.kwargs["response_format"] == {"type": "json_object"}
    finally:
        get_settings.cache_clear()


def test_deepseek_gateway_converts_timeout_to_retryable_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    get_settings.cache_clear()
    try:
        gateway = DeepSeekGateway()
        assert gateway.client.max_retries == 0

        create = Mock(
            side_effect=APITimeoutError(
                request=Request("POST", "https://api.deepseek.com/chat/completions")
            )
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create),
            )
        )
        monkeypatch.setattr(gateway, "client", fake_client)

        from app.core.exceptions import RetryableModelError

        with pytest.raises(RetryableModelError, match="temporarily unavailable"):
            gateway.chat("用户问题")

        create.assert_called_once()
    finally:
        get_settings.cache_clear()


def test_deepseek_gateway_uses_frozen_fallback_only_after_temporary_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        gateway = DeepSeekGateway()
        timeout = APITimeoutError(
            request=Request("POST", "https://api.deepseek.com/chat/completions")
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="fallback answer"))
            ],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1),
        )
        create = Mock(side_effect=[timeout, response])
        gateway.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )

        task = SimpleNamespace(
            id=99,
            model_policy_snapshot={
                "fallback_models": ["deepseek-fallback"],
                "max_attempts": 2,
            },
            model_budget_snapshot={
                "max_calls": 3,
                "max_calls_per_node": 3,
                "max_total_tokens": 1000,
                "max_cost": "1.00",
                "max_repairs": 1,
            },
            model_budget_usage={
                "calls": 0,
                "tokens": 0,
                "cost": "0",
                "calls_by_node": {},
            },
        )

        class Db:
            def get(self, *args, **kwargs):
                return task

            def commit(self):
                return None

            def refresh(self, value):
                return None

            def add(self, value):
                return None

        with model_call_scope(
            Db(), task=task, attempt=SimpleNamespace(id=5), node_name="planner"
        ):
            assert gateway.chat("question") == "fallback answer"

        assert create.call_count == 2
        assert create.call_args_list[0].kwargs["model"] == gateway.model_name
        assert create.call_args_list[1].kwargs["model"] == "deepseek-fallback"
    finally:
        get_settings.cache_clear()


def test_deepseek_gateway_converts_auth_error_to_permanent_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    get_settings.cache_clear()
    try:
        gateway = DeepSeekGateway()
        request = Request("POST", "https://api.deepseek.com/chat/completions")
        response = Response(401, request=request)
        create = Mock(
            side_effect=AuthenticationError(
                "invalid API key",
                response=response,
                body=None,
            )
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create),
            )
        )
        monkeypatch.setattr(gateway, "client", fake_client)

        from app.core.exceptions import PermanentModelError

        with pytest.raises(PermanentModelError, match="configuration is invalid"):
            gateway.chat("用户问题")

        create.assert_called_once()
    finally:
        get_settings.cache_clear()
