"""Render a privacy-safe static timeline for one tenant-scoped task."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from app.db.session import SessionLocal, set_tenant_scope
from app.modules.workflow.audit.events_models import WorkflowEvent
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.audit.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.audit.tool_call import ToolCallRecord
from sqlalchemy import select
from sqlalchemy.orm import Session

_SAFE_CLARIFICATION_SLOTS = frozenset(
    {
        "metric",
        "time_range",
        "comparison_period",
        "region",
        "customer",
        "product",
        "object",
    }
)


def _timestamp(value: datetime | None) -> str:
    return value.isoformat() if value is not None else "-"


def _text(value: object) -> str:
    return escape(str(value)) if value is not None else "-"


def _row(cells: list[object]) -> str:
    return "<tr>" + "".join(f"<td>{_text(cell)}</td>" for cell in cells) + "</tr>"


def _safe_missing_fields(value: object) -> str:
    if not isinstance(value, list):
        return "-"
    fields = [item for item in value if item in _SAFE_CLARIFICATION_SLOTS]
    return ", ".join(fields) if fields else "-"


def render_trace_html(
    *,
    task: AnalysisTask,
    attempts: list[TaskExecutionAttempt],
    events: list[WorkflowEvent],
    model_calls: list[ModelCallRecord],
    tool_calls: list[ToolCallRecord],
) -> str:
    """Render audit metadata only; task text and call payloads never enter HTML."""
    attempt_numbers = {attempt.id: index + 1 for index, attempt in enumerate(attempts)}
    summary_rows = [
        _row(["Task", task.id]),
        _row(["Company", task.company_id]),
        _row(["Status", task.status]),
        _row(["Stage", task.stage]),
        _row(["Created", _timestamp(task.created_at)]),
        _row(["Finished", _timestamp(task.completed_at)]),
        _row(["Duration ms", task.duration_ms]),
        _row(["Clarification status", getattr(task, "clarification_status", None)]),
        _row(
            [
                "Clarification missing fields",
                _safe_missing_fields(
                    getattr(task, "clarification_missing_fields", None)
                ),
            ]
        ),
    ]
    attempt_rows = [
        _row(
            [
                attempt_numbers[attempt.id],
                attempt.status,
                attempt.retry_number,
                attempt.workflow_version,
                _timestamp(attempt.started_at),
                _timestamp(attempt.finished_at),
            ]
        )
        for attempt in attempts
    ]
    timeline_rows: list[tuple[datetime | None, str]] = []
    timeline_rows.extend(
        (
            event.created_at,
            _row(
                [
                    _timestamp(event.created_at),
                    attempt_numbers.get(event.execution_attempt_id, "-"),
                    "workflow",
                    event.event_type,
                    event.node_name,
                    event.tool_name,
                    event.status,
                    event.error_code,
                    event.duration_ms,
                    "-",
                ]
            ),
        )
        for event in events
    )
    timeline_rows.extend(
        (
            call.created_at,
            _row(
                [
                    _timestamp(call.created_at),
                    attempt_numbers.get(call.execution_attempt_id, "-"),
                    "model",
                    call.node_name,
                    call.provider,
                    call.model_name,
                    call.result_category,
                    call.error_code,
                    call.duration_ms,
                    f"tokens={call.prompt_tokens + call.completion_tokens}; cost={call.cost}",
                ]
            ),
        )
        for call in model_calls
    )
    timeline_rows.extend(
        (
            call.created_at,
            _row(
                [
                    _timestamp(call.created_at),
                    attempt_numbers.get(call.execution_attempt_id, "-"),
                    "tool",
                    call.tool_name,
                    "-",
                    "-",
                    call.status,
                    call.error_code,
                    call.duration_ms,
                    "-",
                ]
            ),
        )
        for call in tool_calls
    )
    timeline = "\n".join(
        row
        for _, row in sorted(
            timeline_rows,
            key=lambda item: item[0] or datetime.min.replace(tzinfo=UTC),
        )
    )
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>Task trace {task.id}</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem}}table{{border-collapse:collapse;margin:1rem 0}}td,th{{border:1px solid #bbb;padding:.4rem;text-align:left}}th{{background:#eee}}</style>
</head><body><h1>Task trace {task.id}</h1>
<p>Audit metadata only. This page intentionally excludes task text, prompts, SQL, tool arguments, tool results, report body, and event details.</p>
<h2>Summary</h2><table>{"".join(summary_rows)}</table>
<h2>Attempts</h2><table><tr><th>#</th><th>Status</th><th>Retry</th><th>Workflow version</th><th>Started</th><th>Finished</th></tr>{"".join(attempt_rows)}</table>
<h2>Timeline</h2><table><tr><th>Time</th><th>Attempt</th><th>Kind</th><th>Name</th><th>Provider/node</th><th>Model/tool</th><th>Status</th><th>Error code</th><th>Duration ms</th><th>Usage</th></tr>{timeline}</table>
</body></html>"""


def load_trace(
    db: Session, *, company_id: int, task_id: int
) -> tuple[
    AnalysisTask,
    list[TaskExecutionAttempt],
    list[WorkflowEvent],
    list[ModelCallRecord],
    list[ToolCallRecord],
]:
    """Load only one company's task and its redacted audit records."""
    set_tenant_scope(db, company_id)
    task = db.scalar(
        select(AnalysisTask).where(
            AnalysisTask.id == task_id,
            AnalysisTask.company_id == company_id,
        )
    )
    if task is None:
        raise ValueError("task was not found in the requested company scope")
    attempts = list(
        db.scalars(
            select(TaskExecutionAttempt)
            .where(TaskExecutionAttempt.task_id == task.id)
            .order_by(TaskExecutionAttempt.started_at, TaskExecutionAttempt.id)
        )
    )
    return (
        task,
        attempts,
        list(
            db.scalars(
                select(WorkflowEvent)
                .where(WorkflowEvent.task_id == task.id)
                .order_by(WorkflowEvent.created_at, WorkflowEvent.id)
            )
        ),
        list(
            db.scalars(
                select(ModelCallRecord)
                .where(ModelCallRecord.task_id == task.id)
                .order_by(ModelCallRecord.created_at, ModelCallRecord.id)
            )
        ),
        list(
            db.scalars(
                select(ToolCallRecord)
                .where(ToolCallRecord.task_id == task.id)
                .order_by(ToolCallRecord.created_at, ToolCallRecord.id)
            )
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", type=int, required=True)
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        with SessionLocal() as db:
            task, attempts, events, model_calls, tool_calls = load_trace(
                db, company_id=args.company_id, task_id=args.task_id
            )
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_trace_html(
            task=task,
            attempts=attempts,
            events=events,
            model_calls=model_calls,
            tool_calls=tool_calls,
        ),
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
