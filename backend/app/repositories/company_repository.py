from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import (
    Company,
    BusinessDataSource,
    CompanyMember,
    CompanyInvitation,
    MembershipApplication,
    SchemaSnapshot,
)


def get_company(db: Session, *, company_id: int) -> Company | None:
    return db.get(Company, company_id)


def get_membership_for_user(db: Session, *, user_id: int) -> CompanyMember | None:
    return db.scalar(select(CompanyMember).where(CompanyMember.user_id == user_id))


def get_members_for_company(db: Session, *, company_id: int) -> list[CompanyMember]:
    return list(
        db.scalars(
            select(CompanyMember)
            .where(CompanyMember.company_id == company_id)
            .order_by(CompanyMember.id)
        )
    )


def get_membership(
    db: Session, *, company_id: int, user_id: int
) -> CompanyMember | None:
    return db.scalar(
        select(CompanyMember).where(
            CompanyMember.company_id == company_id, CompanyMember.user_id == user_id
        )
    )


def get_invitation_by_hash(db: Session, *, code_hash: str) -> CompanyInvitation | None:
    return db.scalar(
        select(CompanyInvitation).where(CompanyInvitation.code_hash == code_hash)
    )


def get_invitation_for_company(
    db: Session, *, invitation_id: int, company_id: int
) -> CompanyInvitation | None:
    return db.scalar(
        select(CompanyInvitation).where(
            CompanyInvitation.id == invitation_id,
            CompanyInvitation.company_id == company_id,
        )
    )


def get_invitations_for_company(
    db: Session, *, company_id: int
) -> list[CompanyInvitation]:
    return list(
        db.scalars(
            select(CompanyInvitation)
            .where(CompanyInvitation.company_id == company_id)
            .order_by(CompanyInvitation.id.desc())
        )
    )


def get_application_for_company(
    db: Session, *, application_id: int, company_id: int
) -> MembershipApplication | None:
    return db.scalar(
        select(MembershipApplication).where(
            MembershipApplication.id == application_id,
            MembershipApplication.company_id == company_id,
        )
    )


def get_application_for_user(
    db: Session, *, user_id: int
) -> MembershipApplication | None:
    return db.scalar(
        select(MembershipApplication).where(MembershipApplication.user_id == user_id)
    )


def get_applications_for_company(
    db: Session, *, company_id: int, status: str | None = None
) -> list[MembershipApplication]:
    statement = select(MembershipApplication).where(
        MembershipApplication.company_id == company_id
    )
    if status is not None:
        statement = statement.where(MembershipApplication.status == status)
    return list(db.scalars(statement.order_by(MembershipApplication.id)))


def get_data_source(
    db: Session, *, data_source_id: int, company_id: int
) -> BusinessDataSource | None:
    return db.scalar(
        select(BusinessDataSource).where(
            BusinessDataSource.id == data_source_id,
            BusinessDataSource.company_id == company_id,
        )
    )


def get_latest_snapshot(db: Session, *, data_source_id: int) -> SchemaSnapshot | None:
    return db.scalar(
        select(SchemaSnapshot)
        .where(SchemaSnapshot.data_source_id == data_source_id)
        .order_by(SchemaSnapshot.id.desc())
    )


def get_snapshot(
    db: Session, *, snapshot_id: int, data_source_id: int
) -> SchemaSnapshot | None:
    return db.scalar(
        select(SchemaSnapshot).where(
            SchemaSnapshot.id == snapshot_id,
            SchemaSnapshot.data_source_id == data_source_id,
        )
    )


def get_snapshots(db: Session, *, data_source_id: int) -> list[SchemaSnapshot]:
    return list(
        db.scalars(
            select(SchemaSnapshot)
            .where(SchemaSnapshot.data_source_id == data_source_id)
            .order_by(SchemaSnapshot.id.desc())
        )
    )
