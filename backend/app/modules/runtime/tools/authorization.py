"""The membership and document checks both the worker and the tool service run.

One function, so the two sides of the defence in depth cannot drift apart.
"""

from collections.abc import Collection

from app.modules.documents.models import Documents
from app.modules.documents.repository import allowed_min_view_roles
from app.modules.identity.models import User
from app.modules.organizations.models import CompanyMember
from sqlalchemy.orm import Session


def current_member_allowed(
    db: Session, *, company_id: int, user_id: int, allowed_roles: Collection[str]
) -> bool:
    """True if the user is active and an approved member with an allowed role now."""
    user = db.get(User, user_id)
    membership = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company_id,
            CompanyMember.user_id == user_id,
        )
        .one_or_none()
    )
    return (
        user is not None
        and user.is_active
        and membership is not None
        and membership.status == "approved"
        and membership.role in allowed_roles
    )


def documents_still_visible(
    db: Session, *, company_id: int, user_id: int, document_ids: Collection[int]
) -> bool:
    """True if every document is in the company and visible to the user's role now."""
    membership = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == company_id,
            CompanyMember.user_id == user_id,
        )
        .one_or_none()
    )
    if membership is None:
        return False
    visible = {
        document_id
        for (document_id,) in db.query(Documents.id)
        .filter(
            Documents.id.in_(list(document_ids)),
            Documents.company_id == company_id,
            Documents.min_view_role.in_(allowed_min_view_roles(membership.role)),
        )
        .all()
    }
    return set(document_ids).issubset(visible)
