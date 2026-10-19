import pytest
from app.core.exceptions import VectorSearchError
from app.db.session import set_tenant_scope
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.identity.models import User
from app.modules.knowledge.rag.retrieval import retrieve_evidence
from app.modules.organizations.models import Company
from app.utils.document_chunk import (
    PARAGRAPH_CHUNK_STRATEGY,
    SLIDING_WINDOW_CHUNK_STRATEGY,
)


class _FixedEmbedder:
    def embed(self, _question: str) -> list[float]:
        return [1.0, *([0.0] * 383)]


def _document_with_chunk_variants(db_session):
    user = User(name="retrieval-variants-user", api_key="retrieval-variants-key")
    company = Company(name="retrieval-variants-company")
    db_session.add_all([user, company])
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    document = Documents(
        uploaded_by_user_id=user.id,
        company_id=company.id,
        name="retrieval-variants.txt",
        content="source",
        source="test",
        status="completed",
    )
    db_session.add(document)
    db_session.flush()
    db_session.add_all(
        [
            DocumentChunk(
                document_id=document.id,
                company_id=company.id,
                chunk_strategy=PARAGRAPH_CHUNK_STRATEGY,
                chunk_index=0,
                content="paragraph candidate",
                token_count=2,
                embedding=[0.8, *([0.6] * 383)],
            ),
            DocumentChunk(
                document_id=document.id,
                company_id=company.id,
                chunk_strategy=SLIDING_WINDOW_CHUNK_STRATEGY,
                chunk_index=0,
                content="sliding candidate",
                token_count=2,
                embedding=[1.0, *([0.0] * 383)],
            ),
        ]
    )
    db_session.flush()
    return company, document


def test_dual_chunk_retrieval_runs_two_independent_candidate_routes(db_session) -> None:
    company, document = _document_with_chunk_variants(db_session)

    baseline = retrieve_evidence(
        db_session,
        "question",
        company.id,
        _FixedEmbedder(),
        top_k=1,
        min_score=-1.0,
        document_ids=[document.id],
    )
    dual = retrieve_evidence(
        db_session,
        "question",
        company.id,
        _FixedEmbedder(),
        top_k=1,
        min_score=-1.0,
        document_ids=[document.id],
        chunk_strategies=(
            PARAGRAPH_CHUNK_STRATEGY,
            SLIDING_WINDOW_CHUNK_STRATEGY,
        ),
    )

    assert [evidence.content for evidence in baseline] == ["paragraph candidate"]
    assert [evidence.content for evidence in dual] == ["sliding candidate"]
    assert dual[0].retrieval_strategies == (SLIDING_WINDOW_CHUNK_STRATEGY,)


def test_dual_chunk_retrieval_fails_closed_when_a_frozen_document_lacks_a_variant(
    db_session,
) -> None:
    company, document = _document_with_chunk_variants(db_session)
    db_session.query(DocumentChunk).filter(
        DocumentChunk.document_id == document.id,
        DocumentChunk.chunk_strategy == SLIDING_WINDOW_CHUNK_STRATEGY,
    ).delete()
    db_session.flush()

    with pytest.raises(VectorSearchError, match="Failed to search document vectors"):
        retrieve_evidence(
            db_session,
            "question",
            company.id,
            _FixedEmbedder(),
            document_ids=[document.id],
            chunk_strategies=(
                PARAGRAPH_CHUNK_STRATEGY,
                SLIDING_WINDOW_CHUNK_STRATEGY,
            ),
        )
