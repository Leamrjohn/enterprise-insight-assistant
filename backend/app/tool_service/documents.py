"""T11a: the knowledge model lists and reads the task's documents itself.

Which documents may be read is decided here, on the service, from the task and
the user's current role; the model only names one of them.  A document outside
that set gets the same answer whether it does not exist, belongs to another
company or is above the user's role, so the answer reveals nothing.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.modules.analysis.tool_protocol import ToolOutput
from app.modules.documents.models import Documents
from app.modules.documents.repository import allowed_min_view_roles
from app.modules.organizations.models import CompanyMember
from app.modules.runtime.tools.context import RuntimeContext
from app.modules.workflow.models import AnalysisTaskDocument

PART_CHARS = 4000


def readable_document_ids(db: Session, context: RuntimeContext) -> set[int]:
    """The documents this task froze at creation that the user may still see now.

    Frozen: the AnalysisTaskDocument rows of context.task_id.
    Visible now: in context.company_id, and min_view_role is one of
    allowed_min_view_roles(the user's current role in CompanyMember).
    Use the role in the database, not context.authorized_role: the role may
    have been lowered since the worker signed the context.
    """
    membership = (
        db.query(CompanyMember)
        .filter(
            CompanyMember.company_id == context.company_id,
            CompanyMember.user_id == context.actor_id,
        )
        .one_or_none()
    )
    if membership is None:
        return set()
    rows = (
        db.query(AnalysisTaskDocument.document_id)
        .filter(AnalysisTaskDocument.task_id == context.task_id)
        .all()
    )
    document_ids = {document_id for (document_id,) in rows}
    visible = {
        document_id
        for (document_id,) in db.query(Documents.id)
        .filter(
            Documents.id.in_(document_ids),
            Documents.company_id == context.company_id,
            Documents.min_view_role.in_(allowed_min_view_roles(membership.role)),
        )
        .all()
    }
    return visible


def _readable(db: Session, context: RuntimeContext) -> list[Documents]:
    ids = readable_document_ids(db, context)
    if not ids:
        return []
    return (
        db.query(Documents)
        .filter(
            Documents.id.in_(sorted(ids)), Documents.company_id == context.company_id
        )
        .order_by(Documents.id)
        .all()
    )


def doc_list(db: Session, context: RuntimeContext, arguments: dict[str, Any]) -> Any:
    del arguments  # nothing to choose: the task's documents are the list
    return {
        "documents": [
            {
                "document_id": document.id,
                "name": document.name,
                "kind": document.document_kind,
                "version": document.version_number,
                "effective_from": document.effective_from,
                "effective_to": document.effective_to,
                "applies_to": document.applies_to,
            }
            for document in _readable(db, context)
        ]
    }


def doc_read(db: Session, context: RuntimeContext, arguments: dict[str, Any]) -> Any:
    readable = {document.id: document for document in _readable(db, context)}
    document = readable.get(arguments["document_id"])
    if document is None:
        return ToolOutput(
            success=False,
            error="没有这份可读文档。",
            error_code="tool_arguments_invalid",
            repairable=True,
            model_feedback="没有这份可读文档。可读编号："
            + ("、".join(str(key) for key in readable) or "无"),
        )
    content = document.content or ""
    offset = arguments.get("offset", 0)
    end = offset + PART_CHARS
    return {
        "document_id": document.id,
        "name": document.name,
        "content": content[offset:end],
        "offset": offset,
        "next_offset": end if end < len(content) else None,
    }
