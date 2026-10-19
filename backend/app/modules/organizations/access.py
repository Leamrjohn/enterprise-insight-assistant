"""Centralized current-company authorization dependencies."""

from dataclasses import dataclass
from typing import Literal

from app.db.session import get_db, set_tenant_scope
from app.modules.identity.authentication import get_current_user
from app.modules.identity.models import User
from app.modules.organizations.models import Company, CompanyMember
from app.modules.organizations.repository import get_company, get_membership_for_user
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

CompanyRole = Literal["owner", "admin", "analyst", "viewer"]


@dataclass(frozen=True)
class CurrentCompanyContext:
    user: User
    company: Company
    membership: CompanyMember

    @property
    def role(self) -> str:
        return self.membership.role


def get_current_company_context(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentCompanyContext:
    if not current_user.is_active:
        raise HTTPException(status_code=401, detail="account is inactive")
    membership = get_membership_for_user(db, user_id=current_user.id)
    if membership is None or membership.status != "approved":
        raise HTTPException(
            status_code=403, detail="company membership is not approved"
        )
    company = get_company(db, company_id=membership.company_id)
    if company is None:
        raise HTTPException(status_code=403, detail="company membership is invalid")
    set_tenant_scope(db, company.id)
    request.state.company_id = company.id
    return CurrentCompanyContext(
        user=current_user, company=company, membership=membership
    )


def require_admin(
    context: CurrentCompanyContext = Depends(get_current_company_context),
) -> CurrentCompanyContext:
    if context.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="administrator permission required")
    return context


def require_owner(
    context: CurrentCompanyContext = Depends(get_current_company_context),
) -> CurrentCompanyContext:
    if context.role != "owner":
        raise HTTPException(status_code=403, detail="owner permission required")
    return context


def require_analysis_permission(
    context: CurrentCompanyContext = Depends(get_current_company_context),
) -> CurrentCompanyContext:
    """Allow only roles that may query a company data source."""
    if context.role not in {"owner", "admin", "analyst"}:
        raise HTTPException(status_code=403, detail="analysis permission required")
    return context
