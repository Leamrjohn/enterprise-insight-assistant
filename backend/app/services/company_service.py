"""Transaction and authorization boundary for company setup and onboarding."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.models.company import (
    BusinessDataSource,
    Company,
    CompanyMember,
    CompanyInvitation,
    MembershipApplication,
    SchemaSnapshot,
)
from app.models.user import User
from app.repositories.company_repository import (
    get_application_for_company,
    get_application_for_user,
    get_data_source,
    get_invitation_by_hash,
    get_applications_for_company,
    get_latest_snapshot,
    get_members_for_company,
    get_membership,
    get_snapshot,
)
from app.tools.schema_discovery import discover_postgres_schema


@dataclass(frozen=True)
class CreatedInvitation:
    invitation: CompanyInvitation
    code: str


@dataclass(frozen=True)
class RegisteredApplication:
    application: MembershipApplication


@dataclass(frozen=True)
class BootstrappedOwner:
    user: User
    company: Company


def bootstrap_first_company_owner(
    db: Session, *, name: str, username: str, password: str, company_name: str
) -> BootstrappedOwner:
    """Create the only self-service owner while the platform has no company."""
    if db.query(Company.id).first() is not None:
        raise ValueError("platform already has a company")
    try:
        user = User(
            name=name,
            username=username,
            password_hash=hash_password(password),
            api_key=generate_api_key(),
            is_active=True,
        )
        db.add(user)
        db.flush()
        company = Company(name=company_name)
        db.add(company)
        db.flush()
        db.add(CompanyMember(company_id=company.id, user_id=user.id, role="owner"))
        db.commit()
        db.refresh(user)
        db.refresh(company)
        return BootstrappedOwner(user=user, company=company)
    except Exception:
        db.rollback()
        raise


def create_company(db: Session, *, user_id: int, name: str) -> Company:
    try:
        company = Company(name=name)
        db.add(company)
        db.flush()
        db.add(CompanyMember(company_id=company.id, user_id=user_id, role="owner"))
        db.commit()
        db.refresh(company)
        return company
    except Exception:
        db.rollback()
        raise


def create_company_invitation(
    db: Session,
    *,
    company_id: int,
    created_by_user_id: int,
    max_uses: int,
    expires_at: datetime | None,
) -> CreatedInvitation | None:
    """Create a code whose plaintext form is returned only once."""
    membership = get_membership(db, company_id=company_id, user_id=created_by_user_id)
    if (
        membership is None
        or membership.status != "approved"
        or membership.role not in {"owner", "admin"}
    ):
        return None

    code = generate_api_key()
    invitation = CompanyInvitation(
        company_id=company_id,
        code_hash=hash_api_key(code),
        created_by_user_id=created_by_user_id,
        max_uses=max_uses,
        expires_at=expires_at,
    )
    try:
        db.add(invitation)
        db.commit()
        db.refresh(invitation)
    except Exception:
        db.rollback()
        raise
    return CreatedInvitation(invitation=invitation, code=code)


def register_membership_application(
    db: Session, *, name: str, username: str, password: str, invitation_code: str
) -> RegisteredApplication:
    """Create an inactive account and its only company-join application."""
    invitation = get_invitation_by_hash(db, code_hash=hash_api_key(invitation_code))
    now = datetime.now(timezone.utc)
    if (
        invitation is None
        or not invitation.is_active
        or invitation.used_count >= invitation.max_uses
        or (invitation.expires_at is not None and invitation.expires_at <= now)
    ):
        raise ValueError("invitation code is invalid or unavailable")

    user = User(
        name=name,
        username=username,
        password_hash=hash_password(password),
        api_key=generate_api_key(),
        is_active=False,
    )
    try:
        db.add(user)
        db.flush()
        application = MembershipApplication(
            user_id=user.id,
            company_id=invitation.company_id,
            invitation_id=invitation.id,
            status="pending",
        )
        db.add(application)
        db.commit()
        db.refresh(application)
    except Exception:
        db.rollback()
        raise
    return RegisteredApplication(application=application)


def reapply_to_same_company(
    db: Session, *, username: str, password: str, invitation_code: str
) -> MembershipApplication:
    """Allow a rejected account to resubmit only to its original company."""
    user = db.scalar(select(User).where(User.username == username))
    application = get_application_for_user(db, user_id=user.id) if user else None
    invitation = get_invitation_by_hash(db, code_hash=hash_api_key(invitation_code))
    now = datetime.now(timezone.utc)
    if (
        user is None
        or not verify_password(password, user.password_hash)
        or application is None
        or application.status != "rejected"
        or invitation is None
        or invitation.company_id != application.company_id
        or not invitation.is_active
        or invitation.used_count >= invitation.max_uses
        or (invitation.expires_at is not None and invitation.expires_at <= now)
    ):
        raise ValueError("application cannot be resubmitted with this invitation")
    application.invitation_id = invitation.id
    application.status = "pending"
    application.reviewed_by_user_id = None
    application.reviewed_at = None
    try:
        db.commit()
        db.refresh(application)
    except Exception:
        db.rollback()
        raise
    return application


def approve_membership_application(
    db: Session, *, application_id: int, company_id: int, reviewer_user_id: int
) -> MembershipApplication | None:
    """Approve exactly one pending application in the reviewer's company."""
    application = db.scalar(
        select(MembershipApplication)
        .where(
            MembershipApplication.id == application_id,
            MembershipApplication.company_id == company_id,
        )
        .with_for_update()
    )
    if application is None:
        return None
    if application.status != "pending":
        raise ValueError("application is not pending")
    invitation = db.scalar(
        select(CompanyInvitation)
        .where(
            CompanyInvitation.id == application.invitation_id,
            CompanyInvitation.company_id == company_id,
        )
        .with_for_update()
    )
    if invitation is None or invitation.used_count >= invitation.max_uses:
        raise ValueError("invitation is no longer available")
    if (
        get_membership(db, company_id=company_id, user_id=application.user_id)
        is not None
    ):
        raise ValueError("account already belongs to a company")
    user = db.get(User, application.user_id)
    if user is None:
        raise ValueError("application account no longer exists")

    try:
        db.add(
            CompanyMember(
                company_id=company_id,
                user_id=application.user_id,
                role="analyst",
                status="approved",
            )
        )
        invitation.used_count += 1
        application.status = "approved"
        application.reviewed_by_user_id = reviewer_user_id
        application.reviewed_at = datetime.now(timezone.utc)
        user.is_active = True
        db.commit()
        db.refresh(application)
    except Exception:
        db.rollback()
        raise
    return application


def reject_membership_application(
    db: Session, *, application_id: int, company_id: int, reviewer_user_id: int
) -> MembershipApplication | None:
    application = get_application_for_company(
        db, application_id=application_id, company_id=company_id
    )
    if application is None:
        return None
    if application.status != "pending":
        raise ValueError("application is not pending")
    application.status = "rejected"
    application.reviewed_by_user_id = reviewer_user_id
    application.reviewed_at = datetime.now(timezone.utc)
    try:
        db.commit()
        db.refresh(application)
    except Exception:
        db.rollback()
        raise
    return application


def list_membership_applications(
    db: Session, *, company_id: int, status: str | None = None
) -> list[MembershipApplication]:
    return get_applications_for_company(db, company_id=company_id, status=status)


def create_data_source(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    name: str,
    connection: dict,
    credential_env_var: str,
) -> BusinessDataSource | None:
    membership = get_membership(db, company_id=company_id, user_id=user_id)
    if (
        membership is None
        or membership.status != "approved"
        or membership.role not in {"owner", "admin"}
    ):
        return None
    try:
        source = BusinessDataSource(
            company_id=company_id,
            name=name,
            connection_config=connection,
            credential_env_var=credential_env_var,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return source
    except Exception:
        db.rollback()
        raise


def discover_data_source_schema(
    db: Session, *, data_source_id: int, company_id: int, user_id: int
) -> SchemaSnapshot | None:
    membership = get_membership(db, company_id=company_id, user_id=user_id)
    if (
        membership is None
        or membership.status != "approved"
        or membership.role not in {"owner", "admin"}
    ):
        return None
    source = get_data_source(db, data_source_id=data_source_id, company_id=company_id)
    if source is None:
        return None
    try:
        catalog, fingerprint = discover_postgres_schema(source)
        snapshot = SchemaSnapshot(
            data_source_id=source.id,
            catalog=catalog,
            fingerprint=fingerprint,
            discovered_by_user_id=user_id,
        )
        db.add(snapshot)
        db.flush()
        source.active_schema_snapshot_id = snapshot.id
        source.status, source.last_error = "ready", None
        db.commit()
        db.refresh(snapshot)
        return snapshot
    except Exception as error:
        source.status, source.last_error = (
            "discovery_failed",
            "Schema discovery failed.",
        )
        db.commit()
        raise RuntimeError("Schema discovery failed") from error


def get_current_schema_snapshot(
    db: Session, *, data_source_id: int, company_id: int, user_id: int
) -> SchemaSnapshot | None:
    membership = get_membership(db, company_id=company_id, user_id=user_id)
    if membership is None or membership.status != "approved":
        return None
    source = get_data_source(db, data_source_id=data_source_id, company_id=company_id)
    if source is None:
        return None
    if source.active_schema_snapshot_id is not None:
        return get_snapshot(
            db,
            snapshot_id=source.active_schema_snapshot_id,
            data_source_id=source.id,
        )
    return get_latest_snapshot(db, data_source_id=data_source_id)


def activate_schema_snapshot(
    db: Session, *, data_source_id: int, company_id: int, user_id: int, snapshot_id: int
) -> SchemaSnapshot | None:
    membership = get_membership(db, company_id=company_id, user_id=user_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        return None
    source = get_data_source(db, data_source_id=data_source_id, company_id=company_id)
    snapshot = get_snapshot(db, snapshot_id=snapshot_id, data_source_id=data_source_id)
    if source is None or snapshot is None:
        return None
    source.active_schema_snapshot_id = snapshot.id
    db.commit()
    db.refresh(snapshot)
    return snapshot


def list_company_members(db: Session, *, company_id: int) -> list[CompanyMember]:
    return get_members_for_company(db, company_id=company_id)
