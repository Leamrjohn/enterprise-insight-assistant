import pytest
from pydantic import ValidationError

from app.modules.analysis.sql_candidate import SQLCandidate


def test_parses_valid_model_json() -> None:
    candidate = SQLCandidate.model_validate_json(
        """{
            "sql": "SELECT o.total_amount FROM sales_orders AS o",
            "purpose": "查询已交付订单的销售额"
        }"""
    )

    assert candidate.sql == "SELECT o.total_amount FROM sales_orders AS o"
    assert candidate.purpose == "查询已交付订单的销售额"


def test_rejects_missing_purpose() -> None:
    with pytest.raises(ValidationError):
        SQLCandidate.model_validate({"sql": "SELECT o.id FROM sales_orders AS o"})


def test_rejects_empty_sql() -> None:
    with pytest.raises(ValidationError):
        SQLCandidate.model_validate({"sql": "", "purpose": "查询订单"})


def test_rejects_sql_above_length_limit() -> None:
    with pytest.raises(ValidationError):
        SQLCandidate.model_validate({"sql": "x" * 8_001, "purpose": "查询订单"})
