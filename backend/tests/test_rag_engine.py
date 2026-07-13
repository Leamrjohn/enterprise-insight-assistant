"""测试可靠RAG引擎"""
from app.core.rag.engine import (
    EvidenceRef,
    build_prompt,
    check_sufficiency,
)


def test_build_prompt():
    """测试Prompt组装"""
    evidences = [
        EvidenceRef(chunk_id=1, document_id=10, content="销售额下降了15%"),
        EvidenceRef(chunk_id=2, document_id=10, content="原因是成本上升"),
    ]
    system_prompt, user_prompt = build_prompt("为什么销售额下降", evidences)
    assert isinstance(system_prompt, str)
    assert isinstance(user_prompt, str)
    assert "销售额下降了15%" in user_prompt
    assert "为什么销售额下降" in user_prompt


def test_check_sufficiency_pass():
    """证据充分：条数够且平均分够"""
    evidences = [
        EvidenceRef(chunk_id=1, document_id=1, content="a", score=0.8),
        EvidenceRef(chunk_id=2, document_id=1, content="b", score=0.7),
    ]
    assert check_sufficiency(evidences, min_evidences=1, min_avg_score=0.4) is True


def test_check_sufficiency_fail_low_score():
    """证据不充分：平均分太低"""
    evidences = [
        EvidenceRef(chunk_id=1, document_id=1, content="a", score=0.2),
        EvidenceRef(chunk_id=2, document_id=1, content="b", score=0.1),
    ]
    assert check_sufficiency(evidences, min_evidences=1, min_avg_score=0.4) is False


