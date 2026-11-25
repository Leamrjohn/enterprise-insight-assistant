"""The current-membership check both the worker and the tool service run.

One function, so the two sides of the defence in depth cannot drift apart.
"""

from collections.abc import Collection

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
