"""Register a document as one version of a group and retire what it replaces."""

from datetime import date, timedelta

from app.modules.documents.models import Documents
from sqlalchemy import select
from sqlalchemy.orm import Session


def _dated(document: Documents) -> tuple[int, date]:
    """Every member of a version group was registered with a number and a date."""
    if document.version_number is None or document.effective_from is None:
        raise ValueError("document version sibling is missing its number or date")
    return document.version_number, document.effective_from


def register_document_version(
    db: Session,
    *,
    document: Documents,
    version_group: str,
    version_number: int,
    effective_from: date,
    effective_to: date | None = None,
    document_kind: str | None = None,
    applies_to: str | None = None,
) -> None:
    """Link the document to its neighbours so no two versions overlap in time."""
    if not version_group.strip() or version_number < 1:
        raise ValueError("document version group and number are invalid")
    siblings = (
        db.execute(
            select(Documents)
            .where(
                Documents.company_id == document.company_id,
                Documents.version_group == version_group,
                Documents.id != document.id,
            )
            .order_by(Documents.version_number)
            .with_for_update()
        )
        .scalars()
        .all()
    )
    earlier = [d for d in siblings if _dated(d)[0] < version_number]
    later = [d for d in siblings if _dated(d)[0] > version_number]
    if any(_dated(d)[0] == version_number for d in siblings):
        raise ValueError("document version already registered")
    if (earlier and _dated(earlier[-1])[1] >= effective_from) or (
        later and _dated(later[0])[1] <= effective_from
    ):
        raise ValueError("document version dates must follow version order")

    if later:
        effective_to = _dated(later[0])[1] - timedelta(days=1)
    document.version_group = version_group
    document.version_number = version_number
    document.effective_from = effective_from
    document.effective_to = effective_to
    document.superseded_by_document_id = later[0].id if later else None
    document.document_kind = document_kind
    document.applies_to = applies_to
    if earlier:
        previous = earlier[-1]
        previous.effective_to = effective_from - timedelta(days=1)
        previous.superseded_by_document_id = document.id
    db.flush()
