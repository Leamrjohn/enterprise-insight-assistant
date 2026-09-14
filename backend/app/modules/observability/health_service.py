from sqlalchemy.orm import Session

from app.modules.observability.repository import check_database


def get_readiness_service(db: Session) -> dict[str, str]:
    if not check_database(db):
        return {
            "status": "unavailable",
            "database": "unavailable",
        }

    return {
        "status": "ok",
        "database": "ok",
    }
