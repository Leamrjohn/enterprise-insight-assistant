"""Prepare or clean up the zero-model P0 SQL result-limit candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from app.db.session import SessionLocal, set_tenant_scope
from app.modules.analysis.sql_tool import SQLTool
from app.modules.analysis.tool_protocol import ToolInput
from app.modules.conversations.models import ConversationMessage
from app.modules.identity.models import User
from app.modules.organizations.models import Company, CompanyMember
from app.modules.runtime.tool_runtime import ToolRuntime, ToolRuntimeContext
from app.modules.workflow.execution import claim_execution, finish_execution
from app.modules.workflow.models import AnalysisTask

_QUERY = (
    "SELECT left_order.id FROM sales_orders AS left_order "
    "CROSS JOIN sales_orders AS right_order "
    "CROSS JOIN sales_orders AS third_order LIMIT 100000"
)
_CASE_ID = "sql-result-limit-large-request-capped"


def _register_task_foreign_key_models() -> None:
    """Load the model that owns AnalysisTask.input_message_id before writes."""
    _ = ConversationMessage.__table__


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare(output_dir: Path) -> None:
    _register_task_foreign_key_models()
    run_id = f"p0-sql-result-limit-{uuid4().hex[:12]}"
    user_name = f"{run_id}-user"
    company_name = f"{run_id}-company"
    db = SessionLocal()
    try:
        user = User(name=user_name, api_key=f"{run_id}-api-key")
        company = Company(name=company_name)
        db.add_all([user, company])
        db.flush()
        set_tenant_scope(db, company.id)
        membership = CompanyMember(
            company_id=company.id,
            user_id=user.id,
            role="analyst",
        )
        task = AnalysisTask(
            user_id=user.id,
            company_id=company.id,
            question="P0 SQL result limit candidate",
            status="queued",
            stage="queued",
        )
        db.add_all([membership, task])
        db.commit()

        claim = claim_execution(
            db,
            task_id=task.id,
            celery_task_id=f"{run_id}-celery",
            worker_id="p0-sql-result-limit-candidate",
        )
        if claim is None:
            raise RuntimeError("candidate task claim was unexpectedly rejected")
        result = ToolRuntime(
            db=db,
            attempt=claim.attempt,
            context=ToolRuntimeContext(
                task_id=task.id,
                company_id=company.id,
                allowed_document_ids=frozenset(),
            ),
        ).execute(SQLTool(), ToolInput(parameters={"sql": _QUERY}))
        row_count = (
            len(result.data["rows"])
            if result.success and isinstance(result.data, dict)
            and isinstance(result.data.get("rows"), list)
            else None
        )
        if not result.success or row_count != 1000:
            raise RuntimeError(
                f"expected a successful 1000-row capped result, got {result.error_code=} {row_count=}"
            )
        if not finish_execution(
            db,
            attempt=claim.attempt,
            task_status="completed",
            result_summary="P0 SQL result-limit candidate completed",
            result_data={"terminal_result": {"outcome": "completed"}},
            error_message=None,
        ):
            raise RuntimeError("candidate task lost execution ownership")

        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            output_dir / "sql-result-limit-map.json", {_CASE_ID: task.id}
        )
        _write_json(
            output_dir / "prepare.json",
            {
                "run_id": run_id,
                "state": "sql_result_limit_verified",
                "operation": {
                    "task_id": task.id,
                    "execution_attempt_id": claim.attempt.id,
                    "requested_limit": 100000,
                    "persisted_row_count": row_count,
                    "model_call_count": 0,
                },
                "resource_ids": {
                    "user_id": user.id,
                    "company_id": company.id,
                    "membership_id": membership.id,
                    "task_id": task.id,
                },
                "resource_names": {
                    "user_name": user_name,
                    "company_name": company_name,
                },
            },
        )
    finally:
        db.close()


def cleanup(prepare_path: Path) -> None:
    record = json.loads(prepare_path.read_text(encoding="utf-8"))
    resource_ids = record["resource_ids"]
    resource_names = record["resource_names"]
    db = SessionLocal()
    try:
        company = db.get(Company, resource_ids["company_id"])
        user = db.get(User, resource_ids["user_id"])
        task = db.get(AnalysisTask, resource_ids["task_id"])
        membership = db.get(CompanyMember, resource_ids["membership_id"])
        if (
            company is None
            or user is None
            or task is None
            or membership is None
            or company.name != resource_names["company_name"]
            or user.name != resource_names["user_name"]
            or task.company_id != company.id
            or task.user_id != user.id
            or membership.company_id != company.id
            or membership.user_id != user.id
        ):
            raise RuntimeError("refusing cleanup because the tagged candidate scope changed")
        set_tenant_scope(db, company.id)
        db.delete(task)
        db.flush()
        db.delete(membership)
        db.flush()
        db.delete(user)
        db.flush()
        db.delete(company)
        db.commit()
        _write_json(
            prepare_path.parent / "cleanup.json",
            {"state": "completed", "resource_ids": resource_ids},
        )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        cleanup(args.output_dir / "prepare.json")
    else:
        prepare(args.output_dir)


if __name__ == "__main__":
    main()
