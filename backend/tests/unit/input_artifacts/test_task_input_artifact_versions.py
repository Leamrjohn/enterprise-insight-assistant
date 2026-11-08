import pytest
from app.db.session import set_tenant_scope
from app.modules.conversations.service import (
    ConversationInputArtifactScopeError,
    _resolve_ready_owned_artifact_version_ids,
)
from app.modules.identity.models import User
from app.modules.input_artifacts.versions import create_received_input_artifact_version
from app.modules.organizations.access import CurrentCompanyContext
from app.modules.organizations.models import Company, CompanyMember
from app.modules.workflow.models import AnalysisTaskInputArtifactVersion
from app.modules.workflow.repository import (
    create_task,
    get_task_input_artifact_version_ids,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def _context(db: Session, user: User, *, name: str) -> CurrentCompanyContext:
    company = Company(name=name)
    db.add(company)
    db.flush()
    membership = CompanyMember(
        company_id=company.id,
        user_id=user.id,
        role="analyst",
        status="approved",
    )
    db.add(membership)
    db.flush()
    set_tenant_scope(db, company.id)
    return CurrentCompanyContext(user=user, company=company, membership=membership)


def _ready_version(
    db: Session,
    *,
    context: CurrentCompanyContext,
    suffix: str,
):
    version = create_received_input_artifact_version(
        db,
        company_id=context.company.id,
        uploaded_by_user_id=context.user.id,
        kind="attachment",
        original_filename=f"report-{suffix}.pdf",
        raw_object_key=f"input-artifacts/quarantine/{context.company.id}/{suffix}",
        byte_size=12,
        sha256=(suffix * 64)[:64],
        commit=False,
    )
    version.status = "ready"
    return version


def test_task_freezes_attachment_versions_in_request_order_and_rls_hides_them(
    db_session: Session,
    test_user: User,
) -> None:
    first = _context(db_session, test_user, name="task-artifact-first")
    first_version = _ready_version(db_session, context=first, suffix="a")
    second_version = _ready_version(db_session, context=first, suffix="b")
    task = create_task(
        db_session,
        user_id=test_user.id,
        question="分析附件",
        company_id=first.company.id,
        input_artifact_version_ids=[second_version.id, first_version.id],
    )
    db_session.commit()

    assert get_task_input_artifact_version_ids(db_session, task_id=task.id) == [
        second_version.id,
        first_version.id,
    ]

    other = Company(name="task-artifact-other")
    db_session.add(other)
    db_session.flush()
    db_session.expunge_all()
    set_tenant_scope(db_session, other.id)

    assert (
        db_session.scalar(
            select(AnalysisTaskInputArtifactVersion).where(
                AnalysisTaskInputArtifactVersion.task_id == task.id
            )
        )
        is None
    )


def test_attachment_scope_requires_a_ready_version_owned_by_the_actor(
    db_session: Session,
    test_user: User,
) -> None:
    context = _context(db_session, test_user, name="task-artifact-ready")
    version = _ready_version(db_session, context=context, suffix="c")
    version.status = "parsing"
    db_session.flush()

    with pytest.raises(ConversationInputArtifactScopeError):
        _resolve_ready_owned_artifact_version_ids(
            db_session,
            context=context,
            artifact_version_ids=[version.id],
        )
