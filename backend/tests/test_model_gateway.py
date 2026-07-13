"""测试 Model Gateway"""

import pytest
from app.core.model_gateway_local import LocalModelGateway


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
