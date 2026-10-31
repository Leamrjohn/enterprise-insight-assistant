"""引用校验器 —— 检查答案中的引用是否真实存在"""

from app.db.session import SessionLocal, set_tenant_scope
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.documents.repository import allowed_min_view_roles
from app.modules.organizations.models import CompanyMember
from app.modules.reporting.citation_patterns import CITATION_PATTERN


def validate_citations(
    answer: str,
    user_id: int,
    *,
    allowed_chunk_ids: set[int] | None = None,
) -> tuple[bool, list[int]]:
    """
    校验答案中的引用编号是否真实存在，且当前用户的公司角色可见。

    返回：(is_valid, invalid_ids)
    """
    result = list(CITATION_PATTERN.finditer(answer))
    if not result:
        return (True, [])

    chunk_ids = [int(match.group(1) or match.group(2)) for match in result]
    unique_ids = list(dict.fromkeys(chunk_ids))
    if allowed_chunk_ids is not None:
        out_of_scope = [cid for cid in unique_ids if cid not in allowed_chunk_ids]
        if out_of_scope:
            return False, out_of_scope

    db = SessionLocal()
    invalid = []
    try:
        membership = (
            db.query(CompanyMember)
            .filter(
                CompanyMember.user_id == user_id, CompanyMember.status == "approved"
            )
            .first()
        )
        if membership is None:
            return (False, unique_ids)
        set_tenant_scope(db, membership.company_id)
        for cid in unique_ids:
            chunk = (
                db.query(DocumentChunk)
                .join(Documents, DocumentChunk.document_id == Documents.id)
                .filter(
                    DocumentChunk.id == cid,
                    Documents.company_id == membership.company_id,
                    Documents.min_view_role.in_(
                        allowed_min_view_roles(membership.role)
                    ),
                )
                .first()
            )
            if chunk is None:
                invalid.append(cid)

        if not invalid:
            return (True, [])
        return (False, invalid)
    finally:
        db.close()
