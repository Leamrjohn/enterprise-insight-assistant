"""conversation_summaries: optimistic lock and database-enforced tenant isolation."""

import pytest
from app.db.session import set_tenant_scope
from app.modules.conversations.models import ConversationSummary
from app.modules.conversations.summary import (
    MAX_SUMMARY_ITEMS,
    SUMMARY_SCHEMA,
    empty_summary,
    load_summary,
    save_summary,
)
from sqlalchemy import text
from tests.integration.conversations.test_conversation_state import _conversation


def _saying(text_: str, source: int = 1) -> dict:
    summary = empty_summary()
    summary["items"] = [{"text": text_, "source_message_ids": [source]}]
    summary["covered_through"] = source
    return summary


def test_a_conversation_without_a_row_has_the_empty_summary(db_session) -> None:
    conversation = _conversation(db_session, "summary-empty")
    set_tenant_scope(db_session, conversation.company_id)

    loaded = load_summary(db_session, conversation.id)

    assert loaded.version == 0
    assert loaded.summary == empty_summary()
    assert loaded.summary["schema"] == SUMMARY_SCHEMA


def test_save_inserts_updates_and_a_stale_writer_writes_nothing(db_session) -> None:
    conversation = _conversation(db_session, "summary-save")
    set_tenant_scope(db_session, conversation.company_id)
    ids = {"conversation_id": conversation.id, "company_id": conversation.company_id}

    assert save_summary(db_session, **ids, summary=_saying("华东"), expected_version=0)
    assert save_summary(db_session, **ids, summary=_saying("华南"), expected_version=1)
    # Read version 1, but someone else has already written version 2.
    assert not save_summary(
        db_session, **ids, summary=_saying("华北"), expected_version=1
    )
    assert not save_summary(
        db_session, **ids, summary=_saying("华北"), expected_version=0
    )

    loaded = load_summary(db_session, conversation.id)
    assert loaded.version == 2
    assert loaded.summary["items"][0]["text"] == "华南"


def test_a_summary_with_too_many_items_is_refused(db_session) -> None:
    conversation = _conversation(db_session, "summary-cap")
    set_tenant_scope(db_session, conversation.company_id)
    summary = empty_summary()
    summary["items"] = [
        {"text": f"第{i}条", "source_message_ids": [i]}
        for i in range(1, MAX_SUMMARY_ITEMS + 2)
    ]

    with pytest.raises(ValueError):
        save_summary(
            db_session,
            conversation_id=conversation.id,
            company_id=conversation.company_id,
            summary=summary,
            expected_version=0,
        )


def test_rls_keeps_each_company_to_its_own_summary(db_session) -> None:
    first = _conversation(db_session, "summary-rls-first")
    second = _conversation(db_session, "summary-rls-second")
    for conversation, region in ((first, "华东"), (second, "华南")):
        set_tenant_scope(db_session, conversation.company_id)
        save_summary(
            db_session,
            conversation_id=conversation.id,
            company_id=conversation.company_id,
            summary=_saying(region),
            expected_version=0,
        )

    set_tenant_scope(db_session, second.company_id)
    # No company predicate on purpose: RLS is the backstop.
    rows = db_session.query(ConversationSummary).all()
    assert [row.conversation_id for row in rows] == [second.id]
    assert load_summary(db_session, first.id).version == 0
    assert not save_summary(
        db_session,
        conversation_id=first.id,
        company_id=first.company_id,
        summary=_saying("西部"),
        expected_version=1,
    )

    db_session.info.pop("tenant_company_id")
    db_session.execute(text("RESET app.company_id"))
    assert db_session.query(ConversationSummary).all() == []
