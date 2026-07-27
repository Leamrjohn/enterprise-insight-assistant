"""Current-company management API.  Clients never select a company id."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.company_auth import (
    CurrentCompanyContext,
    get_current_company_context,
    require_admin,
    require_analysis_permission,
)
from app.db.session import get_db
from app.models.company import BusinessDataSource, CompanyMember
from app.models.user import User
from app.repositories.company_repository import get_data_source, get_snapshots
from app.schemas.company import (
    BusinessDataSourceCreate,
    BusinessDataSourceOut,
    AssistantDataSourceOut,
    CompanyCreate,
    CompanyInvitationCreate,
    CompanyInvitationCreated,
    CompanyInvitationOut,
    CompanyMemberOut,
    CompanyMemberUpdate,
    CompanyOut,
    CurrentCompanyOut,
    MembershipApplicationOut,
    SchemaSnapshotOut,
)
from app.services.company_service import (
    activate_schema_snapshot,
    approve_membership_application,
    create_company,
    create_company_invitation,
    create_data_source,
    discover_data_source_schema,
    get_current_schema_snapshot,
    list_company_invitations,
    list_membership_applications,
    list_company_members,
    reject_membership_application,
    revoke_company_invitation,
)

router = APIRouter()


def _source_out(source) -> BusinessDataSourceOut:
    return BusinessDataSourceOut(
        id=source.id,
        name=source.name,
        dialect=source.dialect,
        connection=source.connection_config,
        credential_env_var=source.credential_env_var,
        status=source.status,
        last_error=source.last_error,
        active_schema_snapshot_id=source.active_schema_snapshot_id,
    )


def _member_out(db: Session, member: CompanyMember) -> CompanyMemberOut:
    user = db.get(User, member.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="member not found")
    return CompanyMemberOut(
        id=member.id,
        user_id=user.id,
        user_name=user.name,
        username=user.username,
        is_active=user.is_active,
        role=member.role,
        status=member.status,
        created_at=member.created_at,
    )


def _application_out(db: Session, application) -> MembershipApplicationOut:
    """Expose applicant identity only to an administrator of the same company."""
    user = db.get(User, application.user_id)
    return MembershipApplicationOut(
        id=application.id,
        user_id=application.user_id,
        status=application.status,
        created_at=application.created_at,
        reviewed_at=application.reviewed_at,
        user_name=user.name if user is not None else None,
        username=user.username if user is not None else None,
    )


@router.post(
    "/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED
)
def bootstrap_company(
    request: CompanyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if db.query(CompanyMember).filter(CompanyMember.user_id == current_user.id).first():
        raise HTTPException(
            status_code=409, detail="account already belongs to a company"
        )
    return create_company(db, user_id=current_user.id, name=request.name)


@router.get("/me/company", response_model=CurrentCompanyOut)
def get_my_company(
    context: CurrentCompanyContext = Depends(get_current_company_context),
):
    return CurrentCompanyOut(
        user_id=context.user.id,
        user_name=context.user.name,
        company_id=context.company.id,
        company_name=context.company.name,
        role=context.role,
        membership_status=context.membership.status,
    )


@router.get("/company/resources")
def get_company_resources(
    context: CurrentCompanyContext = Depends(get_current_company_context),
    db: Session = Depends(get_db),
):
    return {
        "company": {"id": context.company.id, "name": context.company.name},
        "role": context.role,
        "data_sources": [
            AssistantDataSourceOut(
                id=source.id,
                name=source.name,
                status=source.status,
                active_schema_snapshot_id=source.active_schema_snapshot_id,
            ).model_dump(mode="json")
            for source in db.query(BusinessDataSource)
            .filter_by(company_id=context.company.id)
            .order_by(BusinessDataSource.id)
            .all()
        ],
    }


@router.get("/company/data-sources", response_model=list[BusinessDataSourceOut])
def list_data_sources(
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return [
        _source_out(source)
        for source in db.query(BusinessDataSource)
        .filter_by(company_id=context.company.id)
        .all()
    ]


@router.get(
    "/company/assistant-data-sources", response_model=list[AssistantDataSourceOut]
)
def list_assistant_data_sources(
    context: CurrentCompanyContext = Depends(require_analysis_permission),
    db: Session = Depends(get_db),
):
    return [
        AssistantDataSourceOut(
            id=source.id,
            name=source.name,
            status=source.status,
            active_schema_snapshot_id=source.active_schema_snapshot_id,
        )
        for source in db.query(BusinessDataSource)
        .filter_by(company_id=context.company.id)
        .order_by(BusinessDataSource.id)
        .all()
    ]


@router.post(
    "/company/data-sources",
    response_model=BusinessDataSourceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_data_source_endpoint(
    request: BusinessDataSourceCreate,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    source = create_data_source(
        db,
        company_id=context.company.id,
        user_id=context.user.id,
        name=request.name,
        connection=request.connection.model_dump(by_alias=True),
        credential_env_var=request.credential_env_var,
    )
    if source is None:
        raise HTTPException(status_code=403, detail="administrator permission required")
    return _source_out(source)


def _current_source_or_404(
    db: Session, context: CurrentCompanyContext, data_source_id: int
):
    source = get_data_source(
        db, data_source_id=data_source_id, company_id=context.company.id
    )
    if source is None:
        raise HTTPException(status_code=404, detail="data source not found")
    return source


@router.get(
    "/company/data-sources/{data_source_id}", response_model=BusinessDataSourceOut
)
def get_data_source_endpoint(
    data_source_id: int,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _source_out(_current_source_or_404(db, context, data_source_id))


@router.post(
    "/company/data-sources/{data_source_id}/discover-schema",
    response_model=SchemaSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
def discover_schema_endpoint(
    data_source_id: int,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _current_source_or_404(db, context, data_source_id)
    snapshot = discover_data_source_schema(
        db,
        data_source_id=data_source_id,
        company_id=context.company.id,
        user_id=context.user.id,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="data source not found")
    return snapshot


@router.get(
    "/company/data-sources/{data_source_id}/schema-snapshots",
    response_model=list[SchemaSnapshotOut],
)
def list_schema_snapshots(
    data_source_id: int,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _current_source_or_404(db, context, data_source_id)
    return get_snapshots(db, data_source_id=data_source_id)


@router.get(
    "/company/data-sources/{data_source_id}/schema-snapshots/current",
    response_model=SchemaSnapshotOut,
)
def get_active_schema_snapshot(
    data_source_id: int,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    snapshot = get_current_schema_snapshot(
        db,
        data_source_id=data_source_id,
        company_id=context.company.id,
        user_id=context.user.id,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="schema snapshot not found")
    return snapshot


@router.post(
    "/company/data-sources/{data_source_id}/schema-snapshots/{snapshot_id}/activate",
    response_model=SchemaSnapshotOut,
)
def activate_schema_snapshot_endpoint(
    data_source_id: int,
    snapshot_id: int,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    snapshot = activate_schema_snapshot(
        db,
        data_source_id=data_source_id,
        company_id=context.company.id,
        user_id=context.user.id,
        snapshot_id=snapshot_id,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="schema snapshot not found")
    return snapshot


@router.get("/company/members", response_model=list[CompanyMemberOut])
def list_members(
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return [
        _member_out(db, member)
        for member in list_company_members(db, company_id=context.company.id)
    ]


@router.post(
    "/company/invitations",
    response_model=CompanyInvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    request: CompanyInvitationCreate,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = create_company_invitation(
        db,
        company_id=context.company.id,
        created_by_user_id=context.user.id,
        max_uses=request.max_uses,
        expires_at=request.expires_at,
    )
    if result is None:
        raise HTTPException(status_code=403, detail="administrator permission required")
    return CompanyInvitationCreated(
        id=result.invitation.id,
        code=result.code,
        max_uses=result.invitation.max_uses,
        expires_at=result.invitation.expires_at,
    )


@router.get("/company/invitations", response_model=list[CompanyInvitationOut])
def list_invitations(
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_company_invitations(db, company_id=context.company.id)


@router.post(
    "/company/invitations/{invitation_id}/revoke",
    response_model=CompanyInvitationOut,
)
def revoke_invitation(
    invitation_id: int,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    invitation = revoke_company_invitation(
        db, invitation_id=invitation_id, company_id=context.company.id
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="invitation not found")
    return invitation


@router.get(
    "/company/membership-applications",
    response_model=list[MembershipApplicationOut],
)
def list_membership_applications_endpoint(
    status: str | None = None,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if status not in {None, "pending", "approved", "rejected"}:
        raise HTTPException(status_code=422, detail="invalid application status")
    return [
        _application_out(db, application)
        for application in list_membership_applications(
            db, company_id=context.company.id, status=status
        )
    ]


@router.post(
    "/company/membership-applications/{application_id}/approve",
    response_model=MembershipApplicationOut,
)
def approve_membership_application_endpoint(
    application_id: int,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        application = approve_membership_application(
            db,
            application_id=application_id,
            company_id=context.company.id,
            reviewer_user_id=context.user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if application is None:
        raise HTTPException(status_code=404, detail="membership application not found")
    return _application_out(db, application)


@router.post(
    "/company/membership-applications/{application_id}/reject",
    response_model=MembershipApplicationOut,
)
def reject_membership_application_endpoint(
    application_id: int,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        application = reject_membership_application(
            db,
            application_id=application_id,
            company_id=context.company.id,
            reviewer_user_id=context.user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if application is None:
        raise HTTPException(status_code=404, detail="membership application not found")
    return _application_out(db, application)


@router.patch("/company/members/{member_id}", response_model=CompanyMemberOut)
def update_member(
    member_id: int,
    request: CompanyMemberUpdate,
    context: CurrentCompanyContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    member = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.id == member_id,
            CompanyMember.company_id == context.company.id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")
    if member.role == "owner" and (
        request.role not in {None, "owner"}
        or request.status in {"disabled", "rejected"}
    ):
        owner_count = (
            db.query(CompanyMember)
            .filter_by(company_id=context.company.id, role="owner", status="approved")
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(status_code=409, detail="cannot change the last owner")
    if request.role is not None:
        member.role = request.role
    if request.status is not None:
        member.status = request.status
        user = db.get(User, member.user_id)
        if user is not None:
            user.is_active = request.status == "approved"
    db.commit()
    db.refresh(member)
    return _member_out(db, member)
