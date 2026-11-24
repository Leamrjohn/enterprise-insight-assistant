"""Read and write a conversation's summary of earlier messages (C9).

The summary keeps what the messages that left the context window said, as at
most ``MAX_SUMMARY_ITEMS`` items, each citing the messages it came from.  Only
code writes it; which proposed items are kept is decided in
``summary_update.apply_summary``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import cast

from app.modules.conversations.models import ConversationSummary
from sqlalchemy import Table, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

SUMMARY_SCHEMA = "conversation-summary/v1"
MAX_SUMMARY_ITEMS = 8
# Where a task's context snapshot keeps the summary frozen at its creation (C9c).
SUMMARY_SNAPSHOT_KEY = "conversation_summary_snapshot"


def empty_summary() -> dict:
    return {
        "schema": SUMMARY_SCHEMA,
        "items": [],
        # The newest message the items cover; 0 when nothing is covered yet.
        "covered_through": 0,
        # Incremental updates since the last full rewrite.
        "incremental_count": 0,
    }


@dataclass(frozen=True)
class LoadedSummary:
    summary: dict
    # 0: the conversation has no row yet, so the first save inserts one.
    version: int


def load_summary(db: Session, conversation_id: int) -> LoadedSummary:
    row = db.execute(
        select(ConversationSummary)
        .where(ConversationSummary.conversation_id == conversation_id)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        return LoadedSummary(empty_summary(), 0)
    return LoadedSummary(copy.deepcopy(row.summary), row.version)


def save_summary(
    db: Session,
    *,
    conversation_id: int,
    company_id: int,
    summary: dict,
    expected_version: int,
    task_id: int | None = None,
) -> bool:
    """Write the summary if nobody changed it since ``expected_version`` was read.

    False means another writer got there first and nothing was written.  Runs
    in the caller's transaction.
    """
    if summary.get("schema") != SUMMARY_SCHEMA:
        raise ValueError(f"summary must use schema {SUMMARY_SCHEMA}")
    if len(summary.get("items", [])) > MAX_SUMMARY_ITEMS:
        raise ValueError(f"summary keeps at most {MAX_SUMMARY_ITEMS} items")
    table = cast(Table, ConversationSummary.__table__)
    if expected_version == 0:
        statement = (
            insert(table)
            .values(
                conversation_id=conversation_id,
                company_id=company_id,
                version=1,
                summary=summary,
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
                summary=summary,
                version=table.c.version + 1,
                last_task_id=task_id,
                updated_at=func.now(),
            )
        )
    written = db.execute(statement.returning(table.c.version)).scalar_one_or_none()
    return written is not None
