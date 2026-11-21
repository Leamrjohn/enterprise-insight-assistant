"""conversation_states: optimistic lock and database-enforced tenant isolation."""

from app.db.session import set_tenant_scope
from app.modules.conversations.models import Conversation, ConversationState
from app.modules.conversations.state import (
    STATE_SCHEMA,
    empty_state,
    load_state,
    save_state,
)
from app.modules.identity.models import User
from app.modules.organizations.models import Company, CompanyMember
from sqlalchemy import text


def _conversation(db_session, suffix: str) -> Conversation:
    user = User(name=f"state-{suffix}", api_key=f"state-key-{suffix}")
    company = Company(name=f"state-company-{suffix}")
    db_session.add_all([user, company])
    db_session.flush()
    db_session.add(
        CompanyMember(
            user_id=user.id, company_id=company.id, role="owner", status="approved"
        )
    )
    conversation = Conversation(user_id=user.id, company_id=company.id)
    db_session.add(conversation)
    db_session.flush()
    return conversation


def _with_region(value: str) -> dict:
    state = empty_state()
    state["constraints"]["region"] = {"op": "include", "value": value}
    return state


def test_a_conversation_without_a_row_has_the_empty_state(db_session) -> None:
    conversation = _conversation(db_session, "empty")
    set_tenant_scope(db_session, conversation.company_id)

    loaded = load_state(db_session, conversation.id)

    assert loaded.version == 0
    assert loaded.state == empty_state()
    assert loaded.state["schema"] == STATE_SCHEMA


def test_save_inserts_then_updates_and_bumps_the_version(db_session) -> None:
    conversation = _conversation(db_session, "save")
    set_tenant_scope(db_session, conversation.company_id)
    ids = {"conversation_id": conversation.id, "company_id": conversation.company_id}

    assert save_state(db_session, **ids, state=_with_region("华东"), expected_version=0)
    first = load_state(db_session, conversation.id)
    assert first.version == 1
    assert first.state["constraints"]["region"]["value"] == "华东"

    assert save_state(
        db_session, **ids, state=_with_region("华南"), expected_version=first.version
    )
    second = load_state(db_session, conversation.id)
    assert second.version == 2
    assert second.state["constraints"]["region"]["value"] == "华南"


def test_a_stale_writer_writes_nothing(db_session) -> None:
    conversation = _conversation(db_session, "stale")
    set_tenant_scope(db_session, conversation.company_id)
    ids = {"conversation_id": conversation.id, "company_id": conversation.company_id}
    save_state(db_session, **ids, state=_with_region("华东"), expected_version=0)
    save_state(db_session, **ids, state=_with_region("华南"), expected_version=1)

    # Read version 1, but someone else has already written version 2.
    assert not save_state(
        db_session, **ids, state=_with_region("华北"), expected_version=1
    )
    # Two first writers: the second insert finds the row and does nothing.
    assert not save_state(
        db_session, **ids, state=_with_region("华北"), expected_version=0
    )
    loaded = load_state(db_session, conversation.id)
    assert loaded.version == 2
    assert loaded.state["constraints"]["region"]["value"] == "华南"


def test_loaded_state_is_a_copy(db_session) -> None:
    conversation = _conversation(db_session, "copy")
    set_tenant_scope(db_session, conversation.company_id)
    save_state(
        db_session,
        conversation_id=conversation.id,
        company_id=conversation.company_id,
        state=_with_region("华东"),
        expected_version=0,
    )
    loaded = load_state(db_session, conversation.id)
    loaded.state["constraints"].clear()

    assert load_state(db_session, conversation.id).state["constraints"]


def test_rls_keeps_each_company_to_its_own_state(db_session) -> None:
    first = _conversation(db_session, "rls-first")
    second = _conversation(db_session, "rls-second")
    for conversation, region in ((first, "华东"), (second, "华南")):
        set_tenant_scope(db_session, conversation.company_id)
        save_state(
            db_session,
            conversation_id=conversation.id,
            company_id=conversation.company_id,
            state=_with_region(region),
            expected_version=0,
        )

    set_tenant_scope(db_session, second.company_id)
    # No company predicate on purpose: RLS is the backstop.
    rows = db_session.query(ConversationState).all()
    assert [row.conversation_id for row in rows] == [second.id]
    assert load_state(db_session, first.id).version == 0
    # Writing another company's row updates nothing.
    assert not save_state(
        db_session,
        conversation_id=first.id,
        company_id=first.company_id,
        state=_with_region("西部"),
        expected_version=1,
    )

    db_session.info.pop("tenant_company_id")
    db_session.execute(text("RESET app.company_id"))
    assert db_session.query(ConversationState).all() == []
