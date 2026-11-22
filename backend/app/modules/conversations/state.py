"""Read and write a conversation's structured state (C6).

The state replaces the regex-found standing constraints: what the user asked to
keep applying, one value per dimension, plus the subject of the last analysis.
Only code writes it, after a task is published; how a Planner proposal becomes
a new state is decided in ``state_update.apply_update`` (C6b).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import cast

from app.modules.conversations.models import ConversationState
from sqlalchemy import Table, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

STATE_SCHEMA = "conversation-state/v1"


def empty_state() -> dict:
    return {
        "schema": STATE_SCHEMA,
        "subject": {"entities": [], "period": None},
        "constraints": {},
        "open_question": None,
    }


@dataclass(frozen=True)
class LoadedState:
    state: dict
    # 0: the conversation has no row yet, so the first save inserts one.
    version: int


def load_state(db: Session, conversation_id: int) -> LoadedState:
    row = db.execute(
        select(ConversationState)
        .where(ConversationState.conversation_id == conversation_id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        return LoadedState(empty_state(), 0)
    return LoadedState(copy.deepcopy(row.state), row.version)


def save_state(
    db: Session,
    *,
    conversation_id: int,
    company_id: int,
    state: dict,
    expected_version: int,
    task_id: int | None = None,
) -> bool:
    """Write the state if nobody changed it since ``expected_version`` was read.

    False means another writer got there first; nothing was written, and the
    caller decides whether to reload and retry.  Runs in the caller's
    transaction, so it commits or rolls back with the publish.
    """
    if state.get("schema") != STATE_SCHEMA:
        raise ValueError(f"state must use schema {STATE_SCHEMA}")
    # Core statements on the table, so RETURNING says whether a row was written
    # (the ORM bulk path does not report it reliably).
    table = cast(Table, ConversationState.__table__)
    if expected_version == 0:
        statement = (
            insert(table)
            .values(
                conversation_id=conversation_id,
                company_id=company_id,
                version=1,
                state=state,
                last_task_id=task_id,
            )
            .on_conflict_do_nothing(index_elements=["conversation_id"])
        )
    else:
        statement = (
            update(table)
            .where(
                table.c.conversation_id == conversation_id,
                table.c.version == expected_version,
            )
            .values(
                state=state,
                version=table.c.version + 1,
                last_task_id=task_id,
                updated_at=func.now(),
            )
        )
    written = db.execute(statement.returning(table.c.version)).scalar_one_or_none()
    return written is not None
