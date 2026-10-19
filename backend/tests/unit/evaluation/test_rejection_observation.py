from app.db.session import set_tenant_scope
from app.modules.evaluation.observation import observation_from_request_rejection
from app.modules.identity.models import User
from app.modules.observability.rejection_audit import AnalysisRequestRejection
from app.modules.organizations.models import Company
from app.modules.workflow.models import AnalysisTask
from sqlalchemy.orm import Session


def _rejection(db: Session, *, request_id: str) -> tuple[int, User]:
    company = Company(name=f"audit-{request_id}")
    user = User(name=f"user-{request_id}", api_key=f"key-{request_id}")
    db.add_all([company, user])
    db.flush()
    set_tenant_scope(db, company.id)
    db.add(
        AnalysisRequestRejection(
            company_id=company.id,
            request_id=request_id,
            operation="conversation_message",
            status_code=404,
        )
    )
    db.flush()
    return company.id, user


def test_request_rejection_observation_proves_no_task_side_effect(
    db_session: Session,
) -> None:
    company_id, _ = _rejection(db_session, request_id="rejection-no-task")

    observation = observation_from_request_rejection(
        db_session,
        case_id="security-cross-company-request",
        company_id=company_id,
        request_id="rejection-no-task",
    )

    assert observation.actual_outcome == "failed"
    assert observation.rejection_observed_status == "passed"
    assert observation.no_side_effects_status == "passed"
    assert observation.model_calls == 0


def test_request_rejection_observation_detects_unexpected_task_side_effect(
    db_session: Session,
) -> None:
    company_id, user = _rejection(db_session, request_id="rejection-with-task")
    db_session.add(
        AnalysisTask(
            user_id=user.id,
            company_id=company_id,
            question="must not exist for a denied request",
            request_id="rejection-with-task",
            status="failed",
            stage="completed",
        )
    )
    db_session.flush()

    observation = observation_from_request_rejection(
        db_session,
        case_id="security-cross-company-request",
        company_id=company_id,
        request_id="rejection-with-task",
    )

    assert observation.no_side_effects_status == "failed"
