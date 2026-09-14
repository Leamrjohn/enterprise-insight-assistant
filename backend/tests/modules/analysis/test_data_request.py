from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.analysis.data_request import DataRequest


def test_data_request_accepts_valid_monthly_comparison():
    request = DataRequest.model_validate(
        {
            "query_id": "regional_revenue_comparison",
            "current_month": "2025-08-01",
            "comparison_month": "2025-07-01",
        }
    )

    assert request.region is None
    assert request.limit == 20
    assert request.current_month == date(2025, 8, 1)


def test_data_request_rejects_unknown_query_id():
    with pytest.raises(ValidationError):
        DataRequest.model_validate(
            {
                "query_id": "run_any_sql",
                "current_month": "2025-08-01",
                "comparison_month": "2025-07-01",
            }
        )


def test_data_request_rejects_invalid_region():
    with pytest.raises(ValidationError):
        DataRequest.model_validate(
            {
                "query_id": "regional_revenue_comparison",
                "region": "SOUTHEAST",
                "current_month": "2025-08-01",
                "comparison_month": "2025-07-01",
            }
        )


def test_data_request_rejects_same_month():
    with pytest.raises(ValidationError):
        DataRequest.model_validate(
            {
                "query_id": "regional_revenue_comparison",
                "current_month": "2025-08-01",
                "comparison_month": "2025-08-01",
            }
        )


def test_data_request_rejects_non_first_day():
    with pytest.raises(ValidationError):
        DataRequest.model_validate(
            {
                "query_id": "regional_revenue_comparison",
                "current_month": "2025-08-15",
                "comparison_month": "2025-07-01",
            }
        )


def test_data_request_rejects_limit_above_boundary():
    with pytest.raises(ValidationError):
        DataRequest.model_validate(
            {
                "query_id": "regional_revenue_comparison",
                "current_month": "2025-08-01",
                "comparison_month": "2025-07-01",
                "limit": 51,
            }
        )
