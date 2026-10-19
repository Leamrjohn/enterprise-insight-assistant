"""Prepare or clean up the zero-model P0 SQL timeout candidate."""

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
from app.modules.runtime.schemas import ToolPolicy
from app.modules.runtime.tool_runtime import ToolRuntime, ToolRuntimeContext
from app.modules.workflow.execution import claim_execution, finish_execution
from app.modules.workflow.models import AnalysisTask

_QUERY = "SELECT sales_orders.id, pg_sleep(0.2) FROM sales_orders LIMIT 1"
_TIMEOUT_MS = 100
_CASE_ID = "sql-statement-timeout-is-classified"


def _register_task_foreign_key_models() -> None:
    """Load the model that owns AnalysisTask.input_message_id before writes."""
    _ = ConversationMessage.__table__


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare(output_dir: Path) -> None:
    _register_task_foreign_key_models()
    run_id = f"p0-sql-timeout-{uuid4().hex[:12]}"
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
            question="P0 SQL statement timeout candidate",
            status="queued",
            stage="queued",
            tool_policy_snapshot=ToolPolicy(
                sql_statement_timeout_ms=_TIMEOUT_MS
            ).model_dump(mode="json"),
        )
        db.add_all([membership, task])
        db.commit()

        claim = claim_execution(
            db,
            task_id=task.id,
            celery_task_id=f"{run_id}-celery",
            worker_id="p0-sql-timeout-candidate",
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
        if result.success or result.error_code != "sql_statement_timeout":
            raise RuntimeError(
                "expected a classified statement timeout, "
                f"got {result.success=} {result.error_code=}"
            )
        if not finish_execution(
            db,
            attempt=claim.attempt,
            task_status="failed",
            result_summary="P0 SQL timeout candidate stopped at statement timeout",
            result_data={"terminal_result": {"outcome": "failed"}},
            error_message=result.error,
        ):
            raise RuntimeError("candidate task lost execution ownership")

        output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(output_dir / "sql-timeout-map.json", {_CASE_ID: task.id})
        _write_json(
            output_dir / "prepare.json",
            {
                "run_id": run_id,
                "state": "sql_timeout_verified",
                "operation": {
                    "task_id": task.id,
                    "execution_attempt_id": claim.attempt.id,
                    "configured_timeout_ms": _TIMEOUT_MS,
                    "query": _QUERY,
                    "persisted_error_code": result.error_code,
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
