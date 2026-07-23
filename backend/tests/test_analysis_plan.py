import pytest
from pydantic import ValidationError

from app.schemas.analysis_plan import AnalysisPlan


def test_plan_requires_at_least_one_source() -> None:
    with pytest.raises(ValidationError, match="at least one source"):
        AnalysisPlan(need_knowledge=False, need_data=False)


def test_plan_accepts_a_knowledge_or_data_source() -> None:
    plan = AnalysisPlan(need_knowledge=True, need_data=False)

    assert plan.need_knowledge is True
    assert plan.need_data is False
