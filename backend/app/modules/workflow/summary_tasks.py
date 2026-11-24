"""Summarize the messages that left a conversation's context window (C9).

Queued after a task is published, outside its transaction.  A summary that
fails, or is never delivered, is caught up by the next publish: covered_through
only moves when a summary is saved.  The call is charged to the task that
queued it, from that task's own summary allowance.
"""

import logging
from dataclasses import dataclass

from app.core.celery_app import celery_app
from app.core.gateway.base import ModelGateway
from app.core.gateway.factory import get_model_gateway
from app.core.settings import get_settings
from app.db.session import SessionLocal, set_tenant_scope
from app.modules.conversations.models import ConversationMessage
from app.modules.conversations.service import MAX_CONTEXT_MESSAGES
from app.modules.conversations.summarizer import OVER_BUDGET, Summarization, summarize
from app.modules.conversations.summary import empty_summary, load_summary, save_summary
from app.modules.conversations.summary_update import (
    apply_summary,
    messages_to_summarize,
    window_start,
)
from app.modules.runtime.context.policies.summary import SUMMARY
from app.modules.runtime.model_governance import model_call_scope
from app.modules.runtime.prompts import get_prompt_registry
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.models import AnalysisTask
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Incremental updates before the summary is rebuilt from all earlier messages.
REWRITE_EVERY = 5
# Messages merged per incremental update; a longer backlog drains over publishes.
MAX_BATCH_MESSAGES = 12


@dataclass
class _Message:
    id: int
    role: str
    content: str | None


def run_summary(db: Session, task_id: int, gateway: ModelGateway) -> str:
    """Update the summary of ``task_id``'s conversation; returns what happened."""
    record = db.get(AnalysisTask, task_id)
    if record is None or record.conversation_id is None or record.company_id is None:
        return "skipped"
    if "summary_max_calls" not in (record.model_budget_snapshot or {}):
        return "skipped"
    attempt = db.execute(
        select(TaskExecutionAttempt)
        .where(TaskExecutionAttempt.task_id == record.id)
        .order_by(TaskExecutionAttempt.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if attempt is None:
        return "skipped"
    # conversation_summaries has forced RLS; scope to the task's company.
    set_tenant_scope(db, record.company_id)
    rows = db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == record.conversation_id)
        .order_by(ConversationMessage.id)
    ).scalars()
    messages = [_Message(row.id, row.role, row.content) for row in rows]
    start = window_start(messages, window_size=MAX_CONTEXT_MESSAGES)
    if start is None:
        return "in_window"
    loaded = load_summary(db, record.conversation_id)
    batch = messages_to_summarize(
        messages,
        covered_through=loaded.summary.get("covered_through", 0),
        window_start_id=start,
        limit=MAX_BATCH_MESSAGES,
    )
    if not batch:
        return "up_to_date"

    rewrite = loaded.summary.get("incremental_count", 0) >= REWRITE_EVERY
    with model_call_scope(
        db,
        task=record,
        attempt=attempt,
        node_name=SUMMARY.node,
        prompt_version=get_prompt_registry().prompt_set_version,
    ):
        result: Summarization | None = None
        if rewrite:
            everything = messages_to_summarize(
                messages, covered_through=0, window_start_id=start, limit=len(messages)
            )
            result = summarize(gateway, summary=empty_summary(), messages=everything)
            if result.error == OVER_BUDGET:
                # Too long to rebuild in one call; no call was made, so merge
                # the next batch as usual instead.
                rewrite, result = False, None
        if result is None:
            result = summarize(gateway, summary=loaded.summary, messages=batch)
            # Only what this call saw counts as covered.
            messages = [m for m in messages if m.id <= batch[-1].id]
    if result.error is not None:
        db.commit()
        logger.warning("Task %s summary proposed nothing: %s", record.id, result.error)
        return result.error

    base = empty_summary() if rewrite else loaded.summary
    summary, rejected = apply_summary(
        base, result.items, messages, window_start_id=start
    )
    summary["incremental_count"] = 0 if rewrite else base["incremental_count"] + 1
    saved = save_summary(
        db,
        conversation_id=record.conversation_id,
        company_id=record.company_id,
        summary=summary,
        expected_version=loaded.version,
        task_id=record.id,
    )
    db.commit()
    logger.info(
        "Task %s summary %s, %d item(s) rejected",
        record.id,
        "saved" if saved else "kept the newer one",
        len(rejected),
    )
    return "saved" if saved else "stale"


@celery_app.task(name="app.modules.workflow.summary_tasks.summarize_conversation")
def summarize_conversation(task_id: int) -> str:
    if get_settings().conversation_summary_mode == "off":
        return "off"
    db = SessionLocal()
    try:
        return run_summary(db, task_id, get_model_gateway())
    finally:
        db.close()
