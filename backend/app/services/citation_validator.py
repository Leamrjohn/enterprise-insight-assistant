"""引用校验器 —— 检查答案中的引用是否真实存在"""

import re

from app.db.session import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.models.documents import Documents
from app.models.company import CompanyMember
from app.repositories.document_repository import allowed_min_view_roles


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
    pattern = r"\[(?:来源|引用)[：:\s]*(\d+)\]"
    result = re.findall(pattern, answer)
    if not result:
        return (True, [])

    chunk_ids = [int(x) for x in result]
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
    except Exception:
        raise
    finally:
        db.close()
