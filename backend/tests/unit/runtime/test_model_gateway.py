"""测试 Model Gateway"""

import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.core.gateway.deepseek import DeepSeekGateway
from app.core.gateway.local import LocalModelGateway
from app.core.gateway.openai import OpenAIGateway
from app.core.settings import get_settings
from app.modules.runtime.model_governance import model_call_scope
from httpx import Request, Response
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)


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
        assert create.call_args.kwargs["extra_body"] == {
            "thinking": {"type": "disabled"}
        }
    finally:
        get_settings.cache_clear()


def test_deepseek_gateway_reserves_system_and_user_prompt_tokens(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        gateway = DeepSeekGateway()
        gateway.count_tokens = len
        gateway.client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=Mock(
                        return_value=SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    message=SimpleNamespace(content="answer")
                                )
                            ],
                            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                        )
                    )
                )
            )
        )
        reserved: dict = {}
        monkeypatch.setattr(
            "app.core.gateway.deepseek.reserve_model_call",
            lambda **kwargs: reserved.update(kwargs),
        )

        gateway.chat("user", system_prompt="system")

        assert reserved["estimated_prompt_tokens"] == len("system") + len("user") + 8
        assert reserved["reserved_completion_tokens"] == gateway.max_output_tokens
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    ("gateway_type", "api_key_name"),
    [(DeepSeekGateway, "DEEPSEEK_API_KEY"), (OpenAIGateway, "OPENAI_API_KEY")],
)
def test_governed_gateway_uses_task_frozen_output_limit(
    monkeypatch, gateway_type, api_key_name
):
    monkeypatch.setenv(api_key_name, "test-key")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "16")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "60")
    if gateway_type is OpenAIGateway:
        monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    try:
        gateway = gateway_type()
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )
        create = Mock(return_value=response)
        gateway.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        reserved: dict = {}
        monkeypatch.setattr(
            f"{gateway.__module__}.reserve_model_call",
            lambda **kwargs: reserved.update(kwargs),
        )
        task = SimpleNamespace(
            model_policy_snapshot={"max_output_tokens": 3, "timeout_seconds": 7}
        )
        with model_call_scope(
            SimpleNamespace(),
            task=task,
            attempt=SimpleNamespace(),
            node_name="planner",
        ):
            assert gateway.chat("prompt") == "answer"

        assert create.call_args.kwargs["max_tokens"] == 3
        assert create.call_args.kwargs["timeout"] == 7
        assert reserved["reserved_completion_tokens"] == 3
        assert reserved["pricing_parameters"]["timeout_seconds"] == 7
    finally:
        get_settings.cache_clear()


def test_deepseek_gateway_records_empty_json_as_retryable_provider_output(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        gateway = DeepSeekGateway()
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))],
            usage=None,
        )
        gateway.client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=response))
            )
        )
        recorded: list[dict] = []
        monkeypatch.setattr(
            "app.core.gateway.deepseek.record_model_call",
            lambda scope, **kwargs: recorded.append(kwargs),
        )

        from app.core.exceptions import RetryableModelError

        with pytest.raises(RetryableModelError, match="empty JSON response"):
            gateway.chat("prompt", json_mode=True)

        assert len(recorded) == 1
        record_with_approximate_duration = recorded[0] | {
            "duration_ms": pytest.approx(recorded[0]["duration_ms"])
        }
        assert record_with_approximate_duration == {
            "provider": "deepseek",
            "model_name": gateway.model_name,
            "duration_ms": pytest.approx(recorded[0]["duration_ms"]),
            "result_category": "retryable_error",
            "error_code": "provider_empty_json_response",
            "prompt_template_id": recorded[0]["prompt_template_id"],
            "prompt_hash": recorded[0]["prompt_hash"],
            "model_parameters": recorded[0]["model_parameters"],
        }
        assert recorded[0]["prompt_template_id"].startswith("system-sha256:")
        assert len(recorded[0]["prompt_hash"]) == 64
    finally:
        get_settings.cache_clear()


def test_deepseek_gateway_degrades_malformed_provider_response(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        gateway = DeepSeekGateway()
        gateway.client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=Mock(return_value=SimpleNamespace()))
            )
        )
        recorded: list[dict] = []
        monkeypatch.setattr(
            "app.core.gateway.deepseek.record_model_call",
            lambda scope, **kwargs: recorded.append(kwargs),
        )

        from app.core.exceptions import RetryableModelError

        with pytest.raises(RetryableModelError, match="malformed response"):
            gateway.chat("prompt")

        assert recorded[0]["result_category"] == "retryable_error"
        assert recorded[0]["error_code"] == "provider_malformed_response"
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


def test_deepseek_gateway_times_out_against_a_slow_local_http_server(monkeypatch):
    class SlowHandler(BaseHTTPRequestHandler):
        request_started_at: float | None = None

        def do_POST(self) -> None:
            type(self).request_started_at = time.monotonic()
            time.sleep(1.5)
            payload = b'{"choices":[{"message":{"content":"late"}}]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except OSError:
                pass

        def log_message(self, format: str, *args: object) -> None:
            return None

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "60")
    get_settings.cache_clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        gateway = DeepSeekGateway()
        gateway.client = OpenAI(
            api_key="test-key",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            max_retries=0,
        )
        recorded: list[dict] = []
        monkeypatch.setattr(
            "app.core.gateway.deepseek.reserve_model_call", lambda **_kwargs: None
        )
        monkeypatch.setattr(
            "app.core.gateway.deepseek.record_model_call",
            lambda _scope, **kwargs: recorded.append(kwargs),
        )
        task = SimpleNamespace(model_policy_snapshot={"timeout_seconds": 1})

        started = time.monotonic()
        with model_call_scope(
            SimpleNamespace(), task=task, attempt=SimpleNamespace(), node_name="planner"
        ):
            from app.core.exceptions import RetryableModelError

            with pytest.raises(RetryableModelError, match="temporarily unavailable"):
                gateway.chat("slow request")

        assert SlowHandler.request_started_at is not None
        assert 0.8 <= time.monotonic() - SlowHandler.request_started_at < 1.3
        assert time.monotonic() - started < 2.5
        assert recorded[0]["error_code"] == "provider_temporary_error"
        assert recorded[0]["model_parameters"]["timeout_seconds"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        get_settings.cache_clear()


@pytest.mark.parametrize("fault", ["connection", "rate_limit"])
def test_deepseek_gateway_converts_transient_provider_faults_to_retryable_error(
    monkeypatch, fault
):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    get_settings.cache_clear()
    try:
        gateway = DeepSeekGateway()
        request = Request("POST", "https://api.deepseek.com/chat/completions")
        if fault == "connection":
            error = APIConnectionError(request=request)
        else:
            error = RateLimitError(
                "rate limited", response=Response(429, request=request), body=None
            )
        create = Mock(side_effect=error)
        gateway.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )

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
                "max_total_tokens": 3000,
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

            def scalar(self, statement):
                return datetime(2040, 1, 1, tzinfo=timezone.utc)

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
