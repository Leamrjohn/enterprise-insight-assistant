"""Keyword recall, and fusing it with vector recall."""

from datetime import date

import pytest
from app.db.session import set_tenant_scope
from app.modules.documents.chunk_repository import add_chunk
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.documents.search_tokens import bigram_tokens, jieba_tokens
from app.modules.documents.versioning import register_document_version
from app.modules.identity.models import User
from app.modules.knowledge.rag.retrieval import _fuse_routes, retrieve_evidence
from app.modules.knowledge.rag.validity import ValidityWindow
from app.modules.organizations.models import Company
from scripts.ops.backfill_chunk_search_vectors import backfill_company

CLOSE = [1.0, *([0.0] * 383)]
FAR = [0.0, 1.0, *([0.0] * 382)]


class _FixedEmbedder:
    def embed(self, _question: str) -> list[float]:
        return CLOSE


def test_jieba_keeps_names_and_codes_and_drops_question_words():
    tokens = jieba_tokens("华东医疗器械客户153的延期原因是什么？")
    assert {"华东", "医疗器械", "153", "延期"} <= set(tokens)
    assert "什么" not in tokens and "的" not in tokens
    assert jieba_tokens("CUST-0009") == ["cust", "0009"]


def test_tokens_cannot_carry_query_syntax():
    for tokenize in (jieba_tokens, bigram_tokens):
        joined = "".join(tokenize("客户' | !x & (y):* 余额"))
        assert not set(joined) & set("'|!&():*")


@pytest.fixture
def company_with_chunks(db_session):
    user = User(name="keyword-user", api_key="keyword-key")
    company = Company(name="keyword-company")
    db_session.add_all([user, company])
    db_session.flush()
    set_tenant_scope(db_session, company.id)

    def add(name: str, content: str, embedding: list[float]) -> Documents:
        document = Documents(
            uploaded_by_user_id=user.id,
            company_id=company.id,
            name=name,
            content=content,
            source="test",
            status="completed",
        )
        db_session.add(document)
        db_session.flush()
        add_chunk(
            db_session,
            document_id=document.id,
            company_id=company.id,
            chunk_strategy="paragraph_v1",
            chunk_index=0,
            content=content,
            token_count=1,
            embedding=embedding,
        )
        return document

    return db_session, company, add


def _search(db, company, question, **kwargs):
    return retrieve_evidence(
        db,
        question,
        company.id,
        _FixedEmbedder(),
        min_score=0.5,
        keyword_tokenizer="jieba",
        **kwargs,
    )


def test_keyword_route_finds_what_vectors_rank_below_the_threshold(company_with_chunks):
    db, company, add = company_with_chunks
    add("named", "客户153 交付延期", FAR)
    add("similar", "一段意思相近的文字", CLOSE)
    results = _search(db, company, "客户153 延期")
    by_name = {evidence.document_name: evidence for evidence in results}
    assert set(by_name) == {"named", "similar"}
    assert by_name["named"].retrieval_strategies == ("keyword:paragraph_v1",)
    assert by_name["similar"].retrieval_strategies == ("paragraph_v1",)
    # The score stays a vector similarity, not a full-text rank.
    assert by_name["named"].score == pytest.approx(0.0)


def test_keyword_route_honours_document_scope(company_with_chunks):
    db, company, add = company_with_chunks
    allowed = add("allowed", "客户153 交付延期", FAR)
    add("other", "客户153 回款正常", FAR)
    results = _search(db, company, "客户153", document_ids=[allowed.id])
    assert [evidence.document_name for evidence in results] == ["allowed"]


def test_keyword_route_honours_validity(company_with_chunks):
    db, company, add = company_with_chunks
    old = add("old", "差旅 报销 上限 450", FAR)
    new = add("new", "差旅 报销 上限 520", FAR)
    for document, number, start in (
        (old, 1, date(2023, 1, 1)),
        (new, 2, date(2025, 1, 1)),
    ):
        register_document_version(
            db,
            document=document,
            version_group="travel",
            version_number=number,
            effective_from=start,
        )
    today = date(2026, 11, 2)
    results = _search(db, company, "差旅报销", validity=ValidityWindow(today, today))
    assert [evidence.document_name for evidence in results] == ["new"]


def test_keyword_route_stays_inside_the_company(company_with_chunks):
    db, _, add = company_with_chunks
    add("mine", "客户153", FAR)
    outsider_user = User(name="keyword-outsider", api_key="keyword-outsider-key")
    outsider = Company(name="keyword-outsider")
    db.add_all([outsider_user, outsider])
    db.flush()
    set_tenant_scope(db, outsider.id)
    document = Documents(
        uploaded_by_user_id=outsider_user.id,
        company_id=outsider.id,
        name="theirs",
        content="客户153",
        source="test",
        sha256="keyword-outsider",
        status="completed",
    )
    db.add(document)
    db.flush()
    add_chunk(
        db,
        document_id=document.id,
        company_id=outsider.id,
        chunk_strategy="paragraph_v1",
        chunk_index=0,
        content="客户153",
        token_count=1,
        embedding=FAR,
    )
    results = _search(db, outsider, "客户153")
    assert [evidence.document_name for evidence in results] == ["theirs"]


def _row(chunk_id, content, score=0.5):
    return {
        "chunk_id": chunk_id,
        "document_id": 1,
        "content": content,
        "score": score,
        "chunk_strategy": "paragraph_v1",
    }


def test_chunk_found_by_both_routes_outranks_one_found_by_either():
    fused = _fuse_routes(
        [
            ("vector", [_row(1, "only vector"), _row(2, "both")]),
            ("keyword", [_row(3, "only keyword"), _row(2, "both")]),
        ]
    )
    assert fused[0].chunk_id == 2
    assert fused[0].retrieval_strategies == ("vector", "keyword")
    assert len(fused) == 3


def test_fusion_uses_rank_not_raw_scores():
    fused = _fuse_routes(
        [
            ("a", [_row(1, "first", 0.2), _row(2, "second", 0.9)]),
        ]
    )
    assert [evidence.chunk_id for evidence in fused] == [1, 2]


def test_same_text_from_two_routes_keeps_the_higher_vector_score():
    fused = _fuse_routes(
        [
            ("a", [_row(1, "same  text", 0.3)]),
            ("b", [_row(2, "same text", 0.8)]),
        ]
    )
    assert len(fused) == 1
    assert fused[0].chunk_id == 2 and fused[0].score == 0.8


def test_backfill_fills_old_chunks_and_does_not_rerun(company_with_chunks):
    db, company, add = company_with_chunks
    document = add("new", "已有索引", FAR)
    db.add(
        DocumentChunk(
            document_id=document.id,
            company_id=company.id,
            chunk_strategy="paragraph_v1",
            chunk_index=1,
            content="客户153 交付延期",
            token_count=1,
            embedding=FAR,
        )
    )
    db.flush()
    assert not _search(db, company, "客户153")
    assert backfill_company(db, company.id) == 1
    assert backfill_company(db, company.id) == 0
    assert [e.document_name for e in _search(db, company, "客户153")] == ["new"]
