from typing import Generator

from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings


settings = get_settings()

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=settings.database_user,
    password=settings.database_password.get_secret_value(),
    host=settings.database_host,
    port=settings.database_port,
    database=settings.database_name,
)

engine = create_engine(
    database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)

SessionLocal = sessionmaker(
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def set_tenant_scope(db: Session, company_id: int) -> None:
    """Bind a Session to one company for the current and later transactions.

    PostgreSQL RLS is the final tenant boundary.  The value is deliberately
    held on the Session as well as set with ``SET LOCAL``: service code may
    commit between workflow stages, which starts a new database transaction.
    The ``after_begin`` hook below reapplies the scope without trusting a
    request, model, or Celery payload after it has been frozen server-side.
    """
    if (
        isinstance(company_id, bool)
        or not isinstance(company_id, int)
        or company_id <= 0
    ):
        raise ValueError("company_id must be a positive integer")

    db.info["tenant_company_id"] = company_id
    db.execute(
        text("SELECT set_config('app.company_id', :company_id, true)"),
        {"company_id": str(company_id)},
    )


@event.listens_for(Session, "after_begin")
def _apply_tenant_scope_on_transaction_start(
    session: Session, transaction, connection
) -> None:
    """Reapply the tenant GUC after commits when a scoped Session is reused."""
    company_id = session.info.get("tenant_company_id")
    if company_id is None:
        return
    connection.execute(
        text("SELECT set_config('app.company_id', :company_id, true)"),
        {"company_id": str(company_id)},
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
