"""M7c: state extraction has its own allowance; the answer path keeps max_calls."""

from uuid import uuid4

import app.modules.workflow.repository as workflow_repository
import app.modules.workflow.tasks as analysis_tasks
import pytest
from app.core.exceptions import RetryableModelError
from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.modules.conversations.state import STATE_SNAPSHOT_KEY
from app.modules.identity.models import User
from app.modules.runtime.context.policies.state_extract import STATE_EXTRACT
from app.modules.runtime.model_governance import (
    ModelBudgetExceeded,
    model_node_scope,
    reserve_model_call,
)
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.repository import create_task
from app.modules.workflow.tasks import process_analysis_task
from tests.integration.workflow.test_tasks import _delete_created_records

BASE = {
    "max_calls": 2,
    "max_calls_per_node": 2,
    "max_repairs": 0,
    "max_total_tokens": 10000,
    "max_cost": "0.11",
}


def test_only_a_task_with_a_frozen_state_gets_the_allowance(
    db_session, test_user, monkeypatch
) -> None:
    settings = get_settings().model_copy(
        update={
            "analysis_task_model_max_calls": 2,
            "analysis_task_model_max_calls_per_node": 2,
            "analysis_task_model_max_repairs": 0,
            "analysis_task_model_max_total_tokens": 10000,
            "analysis_task_model_max_cost": "0.11",
        }
    )
    monkeypatch.setattr(workflow_repository, "get_settings", lambda: settings)

    plain = create_task(db_session, user_id=test_user.id, question="无状态")
    frozen = create_task(
        db_session,
        user_id=test_user.id,
        question="有状态",
        context_snapshot={STATE_SNAPSHOT_KEY: {"state": {}, "version": 0}},
    )

    assert plain.model_budget_snapshot == BASE
    assert frozen.model_budget_snapshot == {
        **BASE,
        "state_extract_max_calls": 1,
        "max_total_tokens": 10000
        + STATE_EXTRACT.budget_tokens
        + settings.llm_max_output_tokens,
    }


def _reserve(node: str, outcomes: list) -> None:
    with model_node_scope(node):
        try:
            reserve_model_call(
                provider="deepseek",
                model_name="budget-test-model",
                estimated_prompt_tokens=1,
                reserved_completion_tokens=1,
            )
            outcomes.append((node, "ok"))
        except ModelBudgetExceeded as error:
            outcomes.append((node, str(error)))


@pytest.mark.parametrize(
    "budget, expected",
    [
        (
            {**BASE, "state_extract_max_calls": 1},
            ["ok", "state extraction budget exhausted", "ok", "ok"],
        ),
        # A task created without the allowance never extracts.
        (BASE, ["state extraction budget exhausted"] * 2 + ["ok", "ok"]),
    ],
)
def test_extraction_spends_its_own_allowance_not_the_answer_calls(
    monkeypatch, budget, expected
) -> None:
    outcomes: list = []

    def run_analysis(*args, **kwargs):
        _reserve(STATE_EXTRACT.node, outcomes)
        _reserve(STATE_EXTRACT.node, outcomes)
        _reserve("planner", outcomes)
        _reserve("planner", outcomes)
        _reserve("reviewer", outcomes)
        raise RetryableModelError("stop after the reservations")

    monkeypatch.setattr(analysis_tasks, "run_analysis", run_analysis)
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"extract-user-{suffix}", api_key=f"extract-key-{suffix}")
        db.add(user)
        db.commit()
        user_id = user.id
        task = AnalysisTask(
            user_id=user_id,
            question="抽取额度",
            status="queued",
            stage="queued",
            model_budget_snapshot=budget,
        )
        db.add(task)
        db.commit()
        task_id = task.id

        with pytest.raises(analysis_tasks.RetryableAnalysisTaskError):
            process_analysis_task.run(task_id=task_id)

        # max_calls is 2: the answer path gets both even after an extraction.
        assert [result for _, result in outcomes] == [
            *expected,
            "model call budget exhausted",
        ]
    finally:
        _delete_created_records(db, task_id, user_id)
