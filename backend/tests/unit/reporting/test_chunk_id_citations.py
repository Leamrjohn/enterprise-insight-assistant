from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.modules.reporting import citation_validation
from app.modules.reporting.numeric_validation import validate_numbers


@pytest.mark.parametrize(
    "label", ["chunk_id 139", "chunk_id:139", "chunk_id：139", "[来源:139]"]
)
def test_citation_label_is_not_a_business_number(label):
    source = [{"chunk_id": 139, "content": "工单 48 件。"}]
    assert validate_numbers(
        f"{label} 记录工单 48 件。", None, knowledge_evidences=source
    ) == (True, [])
    assert (
        validate_numbers(
            f"{label} 记录工单 999 件。", None, knowledge_evidences=source
        )[0]
        is False
    )


@pytest.mark.parametrize(
    "label", ["chunk_id 999", "chunk_id:999", "chunk_id：999", "[来源:999]"]
)
def test_unretrieved_citation_is_rejected_without_database(monkeypatch, label):
    session = MagicMock(
        side_effect=AssertionError("must reject before database access")
    )
    monkeypatch.setattr(citation_validation, "SessionLocal", session)
    assert citation_validation.validate_citations(
        label, 7, allowed_chunk_ids={139}
    ) == (False, [999])
    session.assert_not_called()


@pytest.mark.parametrize(
    "has_membership,has_visible_chunk", [(False, False), (True, False), (True, True)]
)
def test_plain_citation_still_requires_membership_and_visible_chunk(
    monkeypatch, has_membership, has_visible_chunk
):
    db = MagicMock()
    member = SimpleNamespace(company_id=112, role="viewer") if has_membership else None
    db.query.return_value.filter.return_value.first.return_value = member
    query = db.query.return_value.join.return_value.filter.return_value
    query.first.return_value = object() if has_visible_chunk else None
    monkeypatch.setattr(citation_validation, "SessionLocal", lambda: db)
    tenant_scope = MagicMock()
    monkeypatch.setattr(citation_validation, "set_tenant_scope", tenant_scope)
    expected = (True, []) if has_membership and has_visible_chunk else (False, [139])
    assert (
        citation_validation.validate_citations(
            "chunk_id 139", 7, allowed_chunk_ids={139}
        )
        == expected
    )
    if has_membership:
        tenant_scope.assert_called_once_with(db, 112)
        filters = db.query.return_value.join.return_value.filter.call_args.args
        assert len(filters) == 3
    else:
        tenant_scope.assert_not_called()
    db.close.assert_called_once()


@pytest.mark.parametrize(
    "text", ["chunk_id 139.5", "chunk_id 139%", "other_chunk_id 139", "chunk_id 139abc"]
)
def test_non_integer_or_embedded_labels_are_not_exempt_from_number_validation(text):
    assert (
        validate_numbers(text, None, knowledge_evidences=[{"content": "48"}])[0]
        is False
    )
