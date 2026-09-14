"""Database-enforced tenant isolation for document vectors."""

from sqlalchemy import text

from app.db.session import set_tenant_scope
from app.modules.organizations.models import Company, CompanyMember
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.identity.models import User


def _create_company_member(db_session, suffix: str) -> tuple[Company, User]:
    user = User(name=f"tenant-vector-{suffix}", api_key=f"tenant-key-{suffix}")
    company = Company(name=f"tenant-company-{suffix}")
    db_session.add_all([user, company])
    db_session.flush()
    db_session.add(
        CompanyMember(
            user_id=user.id,
            company_id=company.id,
            role="owner",
            status="approved",
        )
    )
    db_session.flush()
    return company, user


def _add_document_chunk(db_session, company: Company, user: User, suffix: str) -> None:
    document = Documents(
        uploaded_by_user_id=user.id,
        company_id=company.id,
        name=f"{suffix}.txt",
        content="tenant scoped evidence",
        source="test",
        sha256=f"tenant-vector-{suffix}",
        status="completed",
    )
    db_session.add(document)
    db_session.flush()
    db_session.add(
        DocumentChunk(
            document_id=document.id,
            company_id=company.id,
            chunk_index=0,
            content=f"evidence for {suffix}",
            token_count=3,
            embedding=[0.1] * 384,
        )
    )
    db_session.flush()


def test_document_chunk_rls_requires_scope_and_prevents_cross_company_reads(
    db_session,
) -> None:
    first_company, first_user = _create_company_member(db_session, "first")
    second_company, second_user = _create_company_member(db_session, "second")

    set_tenant_scope(db_session, first_company.id)
    _add_document_chunk(db_session, first_company, first_user, "first")

    set_tenant_scope(db_session, second_company.id)
    _add_document_chunk(db_session, second_company, second_user, "second")

    set_tenant_scope(db_session, second_company.id)

    # This intentionally has no repository-level company predicate. RLS is
    # the backstop if a future query accidentally omits that predicate.
    second_rows = db_session.query(DocumentChunk).order_by(DocumentChunk.id).all()
    assert [row.company_id for row in second_rows] == [second_company.id]

    set_tenant_scope(db_session, first_company.id)
    first_rows = db_session.query(DocumentChunk).order_by(DocumentChunk.id).all()
    assert [row.company_id for row in first_rows] == [first_company.id]

    db_session.info.pop("tenant_company_id")
    db_session.execute(text("RESET app.company_id"))
    assert db_session.query(DocumentChunk).all() == []
    assert db_session.query(Documents).all() == []
