"""引用校验器 —— 检查答案中的引用是否真实存在"""

import re

from app.db.session import SessionLocal
from app.models.document_chunk import DocumentChunk
from app.models.documents import Documents


def validate_citations(answer: str, user_id: int) -> tuple[bool, list[int]]:
    """
    校验答案中的引用编号是否真实存在，且属于当前用户。

    返回：(is_valid, invalid_ids)
    """
    pattern = r"\[(?:来源|引用)[：:\s]*(\d+)\]"
    result = re.findall(pattern, answer)
    if not result:
        return (True, [])

    chunk_ids = [int(x) for x in result]
    unique_ids = list(dict.fromkeys(chunk_ids))

    db = SessionLocal()
    invalid = []
    try:
        for cid in unique_ids:
            chunk = (
                db.query(DocumentChunk)
                .join(Documents, DocumentChunk.document_id == Documents.id)
                .filter(DocumentChunk.id == cid, Documents.user_id == user_id)
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
