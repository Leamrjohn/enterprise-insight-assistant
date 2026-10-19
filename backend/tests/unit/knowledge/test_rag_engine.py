"""测试可靠RAG引擎"""

from app.modules.knowledge.rag.engine import (
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
    system_prompt, user_prompt, allowed_chunk_ids = build_prompt(
        "为什么销售额下降", evidences
    )
    assert isinstance(system_prompt, str)
    assert isinstance(user_prompt, str)
    assert "销售额下降了15%" in user_prompt
    assert "为什么销售额下降" in user_prompt
    assert allowed_chunk_ids == {1, 2}


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


def test_check_sufficiency_accepts_relevant_chinese_evidence_by_score():
    """中文连续文本不应被空格关键词兜底错误否定。"""
    evidences = [
        EvidenceRef(
            chunk_id=1,
            document_id=1,
            content="华东客户合同到期后暂停常规采购。",
            score=0.64,
        )
    ]

    assert (
        check_sufficiency(
            evidences,
            question="请分析华东区销售额为何下降，并结合内部资料说明原因。",
        )
        is True
    )


def test_build_prompt_allows_only_selected_evidence():
    evidences = [
        EvidenceRef(
            chunk_id=1,
            document_id=10,
            content="FIRST_EVIDENCE",
            score=0.9,
        ),
        EvidenceRef(
            chunk_id=2,
            document_id=10,
            content="SECOND_EVIDENCE",
            score=0.8,
        ),
    ]

    _, user_prompt, allowed_chunk_ids = build_prompt(
        "测试问题",
        evidences,
        max_chars=20,
    )

    assert allowed_chunk_ids == {1}
    assert "FIRST_EVIDENCE" in user_prompt
    assert "SECOND_EVIDENCE" not in user_prompt
