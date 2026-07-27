import pytest
from pydantic import ValidationError

from app.schemas.analysis_plan import AnalysisPlan


def test_plan_rejects_route_mismatch() -> None:
    with pytest.raises(ValidationError, match="route must match"):
        AnalysisPlan(
            route="data_only",
            reason="need data only",
            need_knowledge=True,
            need_data=True,
        )


def test_plan_accepts_knowledge_only_route() -> None:
    plan = AnalysisPlan(
        route="knowledge_only",
        reason="retrieve documents only",
        need_knowledge=True,
        need_data=False,
    )

    assert plan.need_knowledge is True
    assert plan.need_data is False
    assert plan.route == "knowledge_only"


def test_plan_accepts_clarify_route_without_sources() -> None:
    plan = AnalysisPlan(
        route="clarify",
        reason="need more information from user",
        need_knowledge=False,
        need_data=False,
    )

    assert plan.need_knowledge is False
    assert plan.need_data is False
    assert plan.route == "clarify"


def test_plan_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        AnalysisPlan(
            route="data_only",
            reason="",
            need_data=True,
            need_knowledge=False,
        )
