from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.modules.reporting import citation_validation


@pytest.mark.parametrize("failure_stage", ["membership", "tenant_scope", "chunk"])
def test_citation_failure_propagates_and_closes_session(monkeypatch, failure_stage):
    failure = RuntimeError("injected dependency failure")
    membership_query = Mock()
    membership_query.filter.return_value.first.return_value = SimpleNamespace(
        company_id=7, role="analyst"
    )
    chunk_query = Mock()
    db = Mock()
    db.query.side_effect = [membership_query, chunk_query]
    tenant_scope = Mock()
    if failure_stage == "membership":
        membership_query.filter.return_value.first.side_effect = failure
    elif failure_stage == "tenant_scope":
        tenant_scope.side_effect = failure
    else:
        chunk_query.join.return_value.filter.return_value.first.side_effect = failure
    monkeypatch.setattr(citation_validation, "SessionLocal", lambda: db)
    monkeypatch.setattr(citation_validation, "set_tenant_scope", tenant_scope)

    with pytest.raises(RuntimeError) as caught:
        citation_validation.validate_citations("见[来源:42]", user_id=3)

    assert caught.value is failure
    db.close.assert_called_once_with()
    if failure_stage == "membership":
        tenant_scope.assert_not_called()
        assert db.query.call_count == 1
    else:
        tenant_scope.assert_called_once_with(db, 7)
        assert db.query.call_count == (1 if failure_stage == "tenant_scope" else 2)
