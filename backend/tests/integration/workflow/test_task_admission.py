from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import app.modules.workflow.models as workflow_models
import app.modules.workflow.repository as workflow_repository
import pytest
from app.core.exceptions import (
    TaskAdmissionLimitError,
    TaskCapacityLowWatermarkError,
)
from app.core.settings import get_settings
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.identity.models import User
from app.modules.organizations.models import Company
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.repository import cancel_task, create_task


def test_task_freezes_configured_output_token_limit(
    db_session, test_user, monkeypatch
) -> None:
    settings = get_settings().model_copy(update={"llm_max_output_tokens": 37})
    monkeypatch.setattr(workflow_repository, "get_settings", lambda: settings)

    task = create_task(db_session, user_id=test_user.id, question="freeze output")

    assert task.model_policy_snapshot["max_output_tokens"] == 37


def test_task_freezes_server_owned_model_budget(
    db_session, test_user, monkeypatch
) -> None:
    settings = get_settings().model_copy(
        update={
            "analysis_task_model_max_calls": 3,
            "analysis_task_model_max_calls_per_node": 1,
            "analysis_task_model_max_repairs": 0,
            "analysis_task_model_max_total_tokens": 4096,
            "analysis_task_model_max_cost": "0.11",
        }
    )
    monkeypatch.setattr(workflow_repository, "get_settings", lambda: settings)

    task = create_task(db_session, user_id=test_user.id, question="freeze budget")

    assert task.model_budget_snapshot == {
        "max_calls": 3,
        "max_calls_per_node": 1,
        "max_repairs": 0,
        "max_total_tokens": 4096,
        "max_cost": "0.11",
    }


def test_direct_orm_task_default_is_also_server_owned(
    db_session, test_user, monkeypatch
) -> None:
    settings = get_settings().model_copy(
        update={
            "analysis_task_model_max_calls": 2,
            "analysis_task_model_max_calls_per_node": 1,
            "analysis_task_model_max_repairs": 0,
            "analysis_task_model_max_total_tokens": 2048,
            "analysis_task_model_max_cost": "0.09",
        }
    )
    monkeypatch.setattr(workflow_models, "get_settings", lambda: settings)

    task = AnalysisTask(user_id=test_user.id, question="default budget")
    db_session.add(task)
    db_session.flush()

    assert task.model_budget_snapshot == {
        "max_calls": 2,
        "max_calls_per_node": 1,
        "max_repairs": 0,
        "max_total_tokens": 2048,
        "max_cost": "0.09",
    }


def test_capacity_rejection_leaves_no_task_row(
    db_session, test_user, monkeypatch
) -> None:
    company = Company(name=f"capacity-company-{uuid4().hex}")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    monkeypatch.setattr(
        workflow_repository,
        "require_task_capacity",
        lambda _settings: (_ for _ in ()).throw(
            TaskCapacityLowWatermarkError(retry_after_seconds=19)
        ),
    )

    with pytest.raises(TaskCapacityLowWatermarkError):
        create_task(
            db_session,
            user_id=test_user.id,
            company_id=company.id,
            question="must not create a task",
        )

    assert (
        db_session.query(AnalysisTask)
        .filter(AnalysisTask.company_id == company.id)
        .count()
        == 0
    )


def test_concurrent_company_admission_accepts_only_one_task(
    migrated_test_database: None, monkeypatch
) -> None:
    suffix = uuid4().hex
    setup = SessionLocal()
    try:
        user = User(name=f"admission-user-{suffix}", api_key=f"admission-key-{suffix}")
        company = Company(name=f"admission-company-{suffix}")
        setup.add_all((user, company))
        setup.commit()
        user_id, company_id = user.id, company.id
    finally:
        setup.close()

    settings = get_settings().model_copy(
        update={
            "analysis_task_company_inflight_limit": 1,
            "analysis_task_global_inflight_limit": 100,
        }
    )
    monkeypatch.setattr(workflow_repository, "get_settings", lambda: settings)
    barrier = Barrier(2)

    def admit(question: str) -> str:
        db = SessionLocal()
        try:
            set_tenant_scope(db, company_id)
            barrier.wait(timeout=5)
            create_task(
                db,
                user_id=user_id,
                company_id=company_id,
                question=question,
            )
            db.commit()
            return "accepted"
        except TaskAdmissionLimitError:
            db.rollback()
            return "limited"
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(admit, ("first", "second")))

        assert sorted(results) == ["accepted", "limited"]
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(AnalysisTask).filter(
                AnalysisTask.company_id == company_id
            ).delete()
            cleanup.query(Company).filter(Company.id == company_id).delete()
            cleanup.query(User).filter(User.id == user_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()


def test_company_burst_recovers_admission_slots_after_cancellation(
    migrated_test_database: None, monkeypatch
) -> None:
    suffix = uuid4().hex
    setup = SessionLocal()
    try:
        user = User(name=f"burst-user-{suffix}", api_key=f"burst-key-{suffix}")
        company = Company(name=f"burst-company-{suffix}")
        setup.add_all((user, company))
        setup.commit()
        user_id, company_id = user.id, company.id
    finally:
        setup.close()

    settings = get_settings().model_copy(
        update={
            "analysis_task_company_inflight_limit": 3,
            "analysis_task_global_inflight_limit": 100,
        }
    )
    monkeypatch.setattr(workflow_repository, "get_settings", lambda: settings)
    barrier = Barrier(8)

    def admit(question: str) -> str:
        db = SessionLocal()
        try:
            set_tenant_scope(db, company_id)
            barrier.wait(timeout=5)
            create_task(
                db,
                user_id=user_id,
                company_id=company_id,
                question=question,
            )
            db.commit()
            return "accepted"
        except TaskAdmissionLimitError:
            db.rollback()
            return "limited"
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            outcomes = list(executor.map(admit, (f"burst-{i}" for i in range(8))))

        assert outcomes.count("accepted") == 3
        assert outcomes.count("limited") == 5

        recovery = SessionLocal()
        try:
            set_tenant_scope(recovery, company_id)
            tasks = (
                recovery.query(AnalysisTask)
                .filter(AnalysisTask.company_id == company_id)
                .order_by(AnalysisTask.id)
                .all()
            )
            assert [task.status for task in tasks] == ["queued", "queued", "queued"]
            for task in tasks:
                cancel_task(recovery, task)
            recovery.commit()

            resumed = create_task(
                recovery,
                user_id=user_id,
                company_id=company_id,
                question="after-cancellation",
            )
            recovery.commit()
            assert resumed.status == "queued"
        finally:
            recovery.close()
    finally:
        cleanup = SessionLocal()
        try:
            cleanup.query(AnalysisTask).filter(
                AnalysisTask.company_id == company_id
            ).delete()
            cleanup.query(Company).filter(Company.id == company_id).delete()
            cleanup.query(User).filter(User.id == user_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()
