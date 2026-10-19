"""Normalize persisted task facts into a business-evaluation observation."""

import re
from collections import Counter
from decimal import Decimal

from app.db.session import set_tenant_scope
from app.modules.analysis.data.query_contract import ClarificationSpec
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.evaluation.business_schemas import CheckStatus, EvaluationObservation
from app.modules.observability.rejection_audit import AnalysisRequestRejection
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.reviews.models import ReviewRequest
from app.modules.workflow.audit.events_models import WorkflowEvent
from app.modules.workflow.lifecycle.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.audit.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask, AnalysisTaskDocument
from app.modules.workflow.audit.tool_call import ToolCallRecord
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

_TERMINAL_OUTCOMES = {
    "completed": "completed",
    "partial": "partial",
    "failed": "failed",
    "needs_clarification": "needs_clarification",
}

_COST_QUANTUM = Decimal("0.000001")


def _execution_timing_ms(db: Session, *, task: AnalysisTask) -> int | None:
    """Sum completed Worker ownership intervals; queue and review wait are excluded."""
    attempts = list(
        db.scalars(
            select(TaskExecutionAttempt)
            .where(TaskExecutionAttempt.task_id == task.id)
            .order_by(TaskExecutionAttempt.id)
        )
    )
    if not attempts:
        return None
    durations: list[int] = []
    for attempt in attempts:
        if attempt.finished_at is None or attempt.finished_at < attempt.started_at:
            return None
        durations.append(
            max(0, round((attempt.finished_at - attempt.started_at).total_seconds() * 1000))
        )
    return sum(durations)


def _human_review_wait_ms(db: Session, *, task: AnalysisTask) -> int | None:
    """Read a decision wait only when the durable review timestamps are complete."""
    review = db.scalar(select(ReviewRequest).where(ReviewRequest.task_id == task.id))
    if review is None:
        return 0
    if review.reviewed_at is None or review.reviewed_at < review.created_at:
        return None
    return max(0, round((review.reviewed_at - review.created_at).total_seconds() * 1000))


def _check_status(value: object) -> CheckStatus:
    if value is True:
        return "passed"
    if value is False:
        return "failed"
    return "unknown"


def _persisted_entities(value: object) -> list[str] | None:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(entity, str) and entity.strip() for entity in value)
    ):
        return None
    return value


def _persisted_period(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _persisted_data_status(value: object) -> str | None:
    return (
        value
        if value in {"ready", "insufficient_evidence", "failed", "not_run"}
        else None
    )


def _persisted_data_error_code(value: object) -> str | None:
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[a-z0-9_]{1,80}", value)
        else None
    )


def _persisted_clarification_missing_fields(value: object) -> list[str] | None:
    try:
        return ClarificationSpec.model_validate({"missing_slots": value}).missing_slots
    except ValidationError:
        return None


def _status_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _list_count_or_none(value: object) -> int | None:
    return len(value) if isinstance(value, list) else None


def _persisted_result_fingerprint(value: object) -> dict[str, str] | None:
    if (
        not isinstance(value, dict)
        or value.get("algorithm") != "sha256"
        or not isinstance(value.get("value"), str)
        or re.fullmatch(r"[0-9a-f]{64}", value["value"]) is None
    ):
        return None
    return {"algorithm": "sha256", "value": value["value"]}


def _citation_document_paths(
    db: Session, *, task: AnalysisTask, report: FinalAnalysisReport | None
) -> list[str] | None:
    if report is None:
        return None
    cited_chunk_ids = {citation.chunk_id for citation in report.document_citations}
    if not cited_chunk_ids:
        return []
    if task.company_id is None:
        return None
    try:
        set_tenant_scope(db, task.company_id)
        rows = list(
            db.execute(
                select(DocumentChunk.id, DocumentChunk.document_id).where(
                    DocumentChunk.id.in_(cited_chunk_ids),
                    DocumentChunk.company_id == task.company_id,
                )
            )
        )
        if {chunk_id for chunk_id, _ in rows} != cited_chunk_ids:
            return None
        document_ids = {document_id for _, document_id in rows}
        documents = list(
            db.execute(
                select(
                    Documents.id,
                    func.coalesce(Documents.file_path, Documents.source),
                ).where(
                    Documents.id.in_(document_ids),
                    Documents.company_id == task.company_id,
                )
            )
        )
    except SQLAlchemyError:
        return None
    paths_by_document = dict(documents)
    if set(paths_by_document) != document_ids or any(
        not isinstance(path, str) or not path.strip()
        for path in paths_by_document.values()
    ):
        return None
    document_by_chunk = dict(rows)
    return [
        paths_by_document[document_by_chunk[citation.chunk_id]]
        for citation in report.document_citations
    ]


def _citation_security_status(
    db: Session, *, task: AnalysisTask, report: FinalAnalysisReport | None
) -> CheckStatus:
    if report is None or task.company_id is None:
        return "unknown"
    cited_chunk_ids = {citation.chunk_id for citation in report.document_citations}
    try:
        set_tenant_scope(db, task.company_id)
        frozen_document_ids = set(
            db.scalars(
                select(AnalysisTaskDocument.document_id).where(
                    AnalysisTaskDocument.task_id == task.id
                )
            )
        )
        allowed_chunk_ids = set(
            db.scalars(
                select(DocumentChunk.id).where(
                    DocumentChunk.company_id == task.company_id,
                    DocumentChunk.document_id.in_(frozen_document_ids),
                )
            )
        )
    except SQLAlchemyError:
        return "unknown"
    return "passed" if cited_chunk_ids.issubset(allowed_chunk_ids) else "failed"


def _model_cost_observation(
    calls: list[ModelCallRecord],
) -> tuple[str | None, CheckStatus]:
    """Return a total only when every durable model charge is settled."""
    if not calls:
        return format(Decimal(0).quantize(_COST_QUANTUM), "f"), "passed"
    if any(call.billing_status != "settled" or call.cost is None for call in calls):
        return None, "unknown"
    total = sum((Decimal(str(call.cost)) for call in calls), Decimal(0))
    return format(total.quantize(_COST_QUANTUM), "f"), "passed"


def observation_from_persisted_task(
    db: Session, *, case_id: str, task_id: int
) -> EvaluationObservation:
    """Read one terminal task and its model-call ledger without inventing facts."""
    task = db.get(AnalysisTask, task_id)
    if task is None:
        raise ValueError(f"analysis task {task_id} does not exist")
    outcome = _TERMINAL_OUTCOMES.get(task.status)
    if outcome is None:
        raise ValueError(
            f"analysis task {task_id} is not in an evaluable terminal state"
        )

    calls = list(
        db.scalars(
            select(ModelCallRecord)
            .where(ModelCallRecord.task_id == task.id)
            .order_by(ModelCallRecord.id)
        )
    )
    tool_calls = db.scalar(
        select(func.count())
        .select_from(ToolCallRecord)
        .where(ToolCallRecord.task_id == task.id)
    )
    if not isinstance(tool_calls, int):
        tool_calls = 0
    result_data = task.result_data if isinstance(task.result_data, dict) else {}
    terminal_result = result_data.get("terminal_result")
    if (
        isinstance(terminal_result, dict)
        and terminal_result.get("outcome") == "insufficient_evidence"
    ):
        outcome = "insufficient_evidence"
    evaluation_facts = result_data.get("evaluation_facts")
    evaluation_facts = evaluation_facts if isinstance(evaluation_facts, dict) else {}
    report_data = task.report
    report = FinalAnalysisReport.model_validate(report_data) if report_data else None
    is_clarification = outcome == "needs_clarification"
    plan = result_data.get("plan")
    route = plan.get("route") if isinstance(plan, dict) else None
    intent = plan.get("intent") if isinstance(plan, dict) else None
    knowledge_result = result_data.get("knowledge_result")
    review_result = result_data.get("review_result")
    semantic_review = (
        review_result.get("semantic_review")
        if isinstance(review_result, dict)
        else None
    )
    deterministic_validation = result_data.get("deterministic_validation")
    validation_checks = (
        deterministic_validation.get("checks")
        if isinstance(deterministic_validation, dict)
        else None
    )
    numeric_check_status = _check_status(
        validation_checks.get("numbers_valid")
        if isinstance(validation_checks, dict)
        else None
    )
    citation_validation_status = _check_status(
        validation_checks.get("citations_valid")
        if isinstance(validation_checks, dict)
        else None
    )
    deterministic_validation_status = (
        deterministic_validation.get("status")
        if isinstance(deterministic_validation, dict)
        and deterministic_validation.get("status") in {"passed", "failed", "unknown"}
        else "unknown"
    )
    cost, cost_status = _model_cost_observation(calls)
    machine_execution_duration_ms = _execution_timing_ms(db, task=task)
    human_review_wait_ms = _human_review_wait_ms(db, task=task)
    provider_model_calls_by_node = dict(
        sorted(
            Counter(
                call.node_name for call in calls if call.charge_kind == "provider_model"
            ).items()
        )
    )

    return EvaluationObservation(
        case_id=case_id,
        source="persisted_task",
        actual_route=route if isinstance(route, str) else None,
        actual_plan_intent_kind=(
            _status_or_none(intent.get("kind")) if isinstance(intent, dict) else None
        ),
        knowledge_result_status=(
            _status_or_none(knowledge_result.get("status"))
            if isinstance(knowledge_result, dict)
            else None
        ),
        knowledge_evidence_count=(
            _list_count_or_none(knowledge_result.get("evidences"))
            if isinstance(knowledge_result, dict)
            else None
        ),
        semantic_review_verdict=(
            _status_or_none(semantic_review.get("verdict"))
            if isinstance(semantic_review, dict)
            else None
        ),
        reviewer_citation_chunk_count=(
            _list_count_or_none(review_result.get("citation_chunk_ids"))
            if isinstance(review_result, dict)
            else None
        ),
        actual_entities=_persisted_entities(evaluation_facts.get("entities")),
        actual_period=_persisted_period(evaluation_facts.get("period")),
        actual_data_status=_persisted_data_status(evaluation_facts.get("data_status")),
        actual_data_error_code=_persisted_data_error_code(
            evaluation_facts.get("data_error_code")
        ),
        actual_clarification_missing_fields=_persisted_clarification_missing_fields(
            task.clarification_missing_fields
        ),
        actual_result_fingerprint=_persisted_result_fingerprint(
            evaluation_facts.get("result_fingerprint")
        ),
        actual_semantic_result_fingerprint=_persisted_result_fingerprint(
            evaluation_facts.get("semantic_result_fingerprint")
        ),
        actual_confirmed_facts=[fact.statement for fact in report.confirmed_facts]
        if report
        else [],
        actual_supported_claims=(
            [hypothesis.statement for hypothesis in report.hypotheses]
            + [finding.statement for finding in report.document_findings]
            if report
            else []
        ),
        actual_document_qualifications=(
            [
                qualification.statement
                for finding in report.document_findings
                for qualification in finding.qualifications
            ]
            if report
            else []
        ),
        actual_recommendation_actions=[
            recommendation.action for recommendation in report.recommendations
        ]
        if report
        else [],
        returned_chunk_ids=[citation.chunk_id for citation in report.document_citations]
        if report
        else [],
        returned_document_paths=_citation_document_paths(db, task=task, report=report),
        actual_outcome=outcome,
        actual_limitations=[limitation.message for limitation in report.limitations]
        if report
        else [],
        model_calls=sum(call.charge_kind == "provider_model" for call in calls),
        provider_model_calls_by_node=provider_model_calls_by_node,
        local_resource_calls=sum(
            call.charge_kind == "local_resource" for call in calls
        ),
        tokens=sum(call.prompt_tokens + call.completion_tokens for call in calls),
        report_persisted=report is not None,
        numeric_checks_passed=numeric_check_status == "passed",
        numeric_check_status=numeric_check_status,
        citation_validation_status=citation_validation_status,
        deterministic_validation_passed=deterministic_validation_status == "passed",
        deterministic_validation_status=deterministic_validation_status,
        security_check_status=(
            "passed"
            if is_clarification and tool_calls == 0
            else _citation_security_status(db, task=task, report=report)
        ),
        no_side_effects_status=(
            "passed"
            if is_clarification and tool_calls == 0 and report is None
            else "failed"
            if is_clarification
            else "unknown"
        ),
        duration_ms=task.duration_ms,
        machine_execution_duration_ms=machine_execution_duration_ms,
        human_review_wait_ms=human_review_wait_ms,
        cost=cost,
        cost_status=cost_status,
    )


def observation_from_request_rejection(
    db: Session, *, case_id: str, company_id: int, request_id: str
) -> EvaluationObservation:
    """Read a persisted rejection and prove that it created no scoped task."""
    set_tenant_scope(db, company_id)
    rejection = db.scalar(
        select(AnalysisRequestRejection).where(
            AnalysisRequestRejection.company_id == company_id,
            AnalysisRequestRejection.request_id == request_id,
        )
    )
    if rejection is None:
        raise ValueError("analysis request rejection was not found in company scope")
    task_created = db.scalar(
        select(AnalysisTask.id).where(AnalysisTask.request_id == request_id).limit(1)
    )
    return EvaluationObservation(
        case_id=case_id,
        source="request_rejection",
        actual_outcome="failed",
        model_calls=0,
        tokens=0,
        report_persisted=False,
        numeric_checks_passed=False,
        deterministic_validation_passed=False,
        security_check_status="passed",
        rejection_observed_status="passed",
        no_side_effects_status="passed" if task_created is None else "failed",
        duration_ms=0,
        cost=format(Decimal(0).quantize(_COST_QUANTUM), "f"),
        cost_status="passed",
    )


def observation_from_runtime_tool_rejection(
    db: Session, *, case_id: str, task_id: int
) -> EvaluationObservation:
    """Read a persisted Runtime denial and prove its tool never executed."""
    task = db.get(AnalysisTask, task_id)
    if task is None or task.company_id is None:
        raise ValueError("runtime tool rejection task was not found in company scope")
    set_tenant_scope(db, task.company_id)
    task = db.scalar(
        select(AnalysisTask).where(
            AnalysisTask.id == task_id,
            AnalysisTask.company_id == task.company_id,
        )
    )
    if task is None:
        raise ValueError("runtime tool rejection task was not found in company scope")
    calls = list(
        db.scalars(
            select(ModelCallRecord)
            .where(ModelCallRecord.task_id == task.id)
            .order_by(ModelCallRecord.id)
        )
    )
    tool_calls = list(
        db.scalars(
            select(ToolCallRecord)
            .where(ToolCallRecord.task_id == task.id)
            .order_by(ToolCallRecord.id)
        )
    )
    denied = [call for call in tool_calls if call.status == "denied"]
    denial_observed = bool(denied)
    execution_prevented = denial_observed and all(
        call.status == "denied" for call in tool_calls
    )
    cost, cost_status = _model_cost_observation(calls)
    return EvaluationObservation(
        case_id=case_id,
        source="runtime_tool_rejection",
        actual_outcome="failed",
        model_calls=sum(call.charge_kind == "provider_model" for call in calls),
        provider_model_calls_by_node=dict(
            sorted(
                Counter(
                    call.node_name
                    for call in calls
                    if call.charge_kind == "provider_model"
                ).items()
            )
        ),
        local_resource_calls=sum(
            call.charge_kind == "local_resource" for call in calls
        ),
        tokens=sum(call.prompt_tokens + call.completion_tokens for call in calls),
        report_persisted=bool(task.report),
        numeric_checks_passed=False,
        deterministic_validation_passed=False,
        security_check_status=(
            "passed" if execution_prevented else "failed"
        ),
        runtime_tool_denial_status="passed" if denial_observed else "failed",
        tool_execution_prevented_status=(
            "passed" if execution_prevented else "failed"
        ),
        actual_tool_denial_codes=sorted(
            {
                call.error_code
                for call in denied
                if isinstance(call.error_code, str) and call.error_code
            }
        ),
        duration_ms=task.duration_ms,
        cost=cost,
        cost_status=cost_status,
    )


def observation_from_sql_validation_rejection(
    db: Session, *, case_id: str, task_id: int
) -> EvaluationObservation:
    """Read a persisted SQL validation failure and its lack of business result."""
    task = db.get(AnalysisTask, task_id)
    if task is None or task.company_id is None:
        raise ValueError("sql validation rejection task was not found in company scope")
    set_tenant_scope(db, task.company_id)
    task = db.scalar(
        select(AnalysisTask).where(
            AnalysisTask.id == task_id,
            AnalysisTask.company_id == task.company_id,
        )
    )
    if task is None:
        raise ValueError("sql validation rejection task was not found in company scope")
    calls = list(
        db.scalars(
            select(ModelCallRecord)
            .where(ModelCallRecord.task_id == task.id)
            .order_by(ModelCallRecord.id)
        )
    )
    tool_calls = list(
        db.scalars(
            select(ToolCallRecord)
            .where(ToolCallRecord.task_id == task.id)
            .order_by(ToolCallRecord.id)
        )
    )
    validation_failures = [
        call
        for call in tool_calls
        if call.tool_name == "sql_query"
        and call.status == "failed"
        and call.error_code == "sql_validation_error"
    ]
    validation_observed = bool(validation_failures)
    result_prevented = (
        validation_observed
        and all(call.status == "failed" for call in tool_calls)
        and not task.report
    )
    cost, cost_status = _model_cost_observation(calls)
    return EvaluationObservation(
        case_id=case_id,
        source="sql_validation_rejection",
        actual_outcome="failed",
        model_calls=sum(call.charge_kind == "provider_model" for call in calls),
        provider_model_calls_by_node=dict(
            sorted(
                Counter(
                    call.node_name
                    for call in calls
                    if call.charge_kind == "provider_model"
                ).items()
            )
        ),
        local_resource_calls=sum(
            call.charge_kind == "local_resource" for call in calls
        ),
        tokens=sum(call.prompt_tokens + call.completion_tokens for call in calls),
        report_persisted=bool(task.report),
        numeric_checks_passed=False,
        deterministic_validation_passed=False,
        security_check_status="passed" if result_prevented else "failed",
        sql_validation_rejection_status=(
            "passed" if validation_observed else "failed"
        ),
        business_result_prevented_status=(
            "passed" if result_prevented else "failed"
        ),
        actual_sql_validation_codes=sorted(
            {
                call.error_code
                for call in validation_failures
                if isinstance(call.error_code, str) and call.error_code
            }
        ),
        duration_ms=task.duration_ms,
        cost=cost,
        cost_status=cost_status,
    )


def observation_from_sql_result_limit(
    db: Session, *, case_id: str, task_id: int
) -> EvaluationObservation:
    """Read one terminal SQL call and its persisted privacy-safe row count."""
    task = db.get(AnalysisTask, task_id)
    if task is None or task.company_id is None:
        raise ValueError("sql result limit task was not found in company scope")
    set_tenant_scope(db, task.company_id)
    task = db.scalar(
        select(AnalysisTask).where(
            AnalysisTask.id == task_id,
            AnalysisTask.company_id == task.company_id,
        )
    )
    if task is None:
        raise ValueError("sql result limit task was not found in company scope")
    calls = list(
        db.scalars(
            select(ModelCallRecord)
            .where(ModelCallRecord.task_id == task.id)
            .order_by(ModelCallRecord.id)
        )
    )
    tool_calls = list(
        db.scalars(
            select(ToolCallRecord)
            .where(ToolCallRecord.task_id == task.id)
            .order_by(ToolCallRecord.id)
        )
    )
    bounded_calls = [
        call
        for call in tool_calls
        if call.tool_name == "sql_query"
        and call.status == "succeeded"
        and isinstance(call.metadata_json.get("row_count"), int)
        and not isinstance(call.metadata_json.get("row_count"), bool)
    ]
    row_count = bounded_calls[0].metadata_json["row_count"] if len(bounded_calls) == 1 else None
    completed = (
        len(tool_calls) == 1
        and row_count is not None
        and task.status == "completed"
        and task.active_execution_id is None
    )
    cost, cost_status = _model_cost_observation(calls)
    return EvaluationObservation(
        case_id=case_id,
        source="sql_result_limit",
        actual_outcome="completed" if completed else "failed",
        model_calls=sum(call.charge_kind == "provider_model" for call in calls),
        provider_model_calls_by_node=dict(
            sorted(
                Counter(
                    call.node_name
                    for call in calls
                    if call.charge_kind == "provider_model"
                ).items()
            )
        ),
        local_resource_calls=sum(
            call.charge_kind == "local_resource" for call in calls
        ),
        tokens=sum(call.prompt_tokens + call.completion_tokens for call in calls),
        report_persisted=bool(task.report),
        numeric_checks_passed=False,
        deterministic_validation_passed=False,
        security_check_status="passed" if completed else "failed",
        sql_result_limit_status="passed" if completed else "failed",
        actual_sql_result_row_count=row_count,
        duration_ms=task.duration_ms,
        cost=cost,
        cost_status=cost_status,
    )


def observation_from_sql_timeout(
    db: Session, *, case_id: str, task_id: int
) -> EvaluationObservation:
    """Read one persisted SQL timeout and prove it produced no business result."""
    task = db.get(AnalysisTask, task_id)
    if task is None or task.company_id is None:
        raise ValueError("sql timeout task was not found in company scope")
    set_tenant_scope(db, task.company_id)
    task = db.scalar(
        select(AnalysisTask).where(
            AnalysisTask.id == task_id,
            AnalysisTask.company_id == task.company_id,
        )
    )
    if task is None:
        raise ValueError("sql timeout task was not found in company scope")
    calls = list(
        db.scalars(
            select(ModelCallRecord)
            .where(ModelCallRecord.task_id == task.id)
            .order_by(ModelCallRecord.id)
        )
    )
    tool_calls = list(
        db.scalars(
            select(ToolCallRecord)
            .where(ToolCallRecord.task_id == task.id)
            .order_by(ToolCallRecord.id)
        )
    )
    timed_out_calls = [
        call
        for call in tool_calls
        if call.tool_name == "sql_query"
        and call.status == "failed"
        and call.error_code == "sql_statement_timeout"
    ]
    timeout_observed = bool(timed_out_calls)
    result_prevented = (
        len(tool_calls) == 1
        and len(timed_out_calls) == 1
        and task.status == "failed"
        and task.active_execution_id is None
        and not task.report
    )
    cost, cost_status = _model_cost_observation(calls)
    return EvaluationObservation(
        case_id=case_id,
        source="sql_timeout",
        actual_outcome="failed",
        model_calls=sum(call.charge_kind == "provider_model" for call in calls),
        provider_model_calls_by_node=dict(
            sorted(
                Counter(
                    call.node_name
                    for call in calls
                    if call.charge_kind == "provider_model"
                ).items()
            )
        ),
        local_resource_calls=sum(
            call.charge_kind == "local_resource" for call in calls
        ),
        tokens=sum(call.prompt_tokens + call.completion_tokens for call in calls),
        report_persisted=bool(task.report),
        numeric_checks_passed=False,
        deterministic_validation_passed=False,
        security_check_status="passed" if result_prevented else "failed",
        sql_timeout_status="passed" if timeout_observed else "failed",
        sql_timeout_result_prevented_status=(
            "passed" if result_prevented else "failed"
        ),
        actual_sql_timeout_codes=sorted(
            {
                call.error_code
                for call in timed_out_calls
                if isinstance(call.error_code, str) and call.error_code
            }
        ),
        duration_ms=task.duration_ms,
        cost=cost,
        cost_status=cost_status,
    )


def observation_from_duplicate_delivery(
    db: Session, *, case_id: str, task_id: int
) -> EvaluationObservation:
    """Read a rejected duplicate claim and the resulting one-attempt terminal task."""
    task = db.get(AnalysisTask, task_id)
    if task is None or task.company_id is None:
        raise ValueError("duplicate delivery task was not found in company scope")
    set_tenant_scope(db, task.company_id)
    attempts = list(
        db.scalars(
            select(TaskExecutionAttempt)
            .where(TaskExecutionAttempt.task_id == task.id)
            .order_by(TaskExecutionAttempt.id)
        )
    )
    events = list(
        db.scalars(
            select(WorkflowEvent)
            .where(WorkflowEvent.task_id == task.id)
            .order_by(WorkflowEvent.id)
        )
    )
    calls = list(
        db.scalars(
            select(ModelCallRecord)
            .where(ModelCallRecord.task_id == task.id)
            .order_by(ModelCallRecord.id)
        )
    )
    rejected = [
        event
        for event in events
        if event.event_type == "execution_claim_rejected"
        and event.error_code == "execution_already_claimed"
        and event.details == {"operation": "claim_execution"}
    ]
    duplicate_observed = bool(rejected)
    execution_prevented = (
        duplicate_observed
        and len(attempts) == 1
        and task.status == "completed"
        and task.active_execution_id is None
    )
    cost, cost_status = _model_cost_observation(calls)
    return EvaluationObservation(
        case_id=case_id,
        source="duplicate_delivery",
        actual_outcome="completed" if execution_prevented else "failed",
        model_calls=sum(call.charge_kind == "provider_model" for call in calls),
        provider_model_calls_by_node=dict(
            sorted(
                Counter(
                    call.node_name
                    for call in calls
                    if call.charge_kind == "provider_model"
                ).items()
            )
        ),
        local_resource_calls=sum(
            call.charge_kind == "local_resource" for call in calls
        ),
        tokens=sum(call.prompt_tokens + call.completion_tokens for call in calls),
        report_persisted=bool(task.report),
        numeric_checks_passed=False,
        deterministic_validation_passed=False,
        security_check_status="passed" if execution_prevented else "failed",
        duplicate_delivery_status="passed" if duplicate_observed else "failed",
        duplicate_execution_prevented_status=(
            "passed" if execution_prevented else "failed"
        ),
        actual_duplicate_delivery_codes=sorted(
            {
                event.error_code
                for event in rejected
                if isinstance(event.error_code, str) and event.error_code
            }
        ),
        duration_ms=task.duration_ms,
        cost=cost,
        cost_status=cost_status,
    )


def observation_from_execution_fence(
    db: Session, *, case_id: str, task_id: int
) -> EvaluationObservation:
    """Read a persisted cancellation and rejected stale terminal write."""
    task = db.get(AnalysisTask, task_id)
    if task is None or task.company_id is None:
        raise ValueError("execution fence task was not found in company scope")
    set_tenant_scope(db, task.company_id)
    attempts = list(
        db.scalars(
            select(TaskExecutionAttempt).where(TaskExecutionAttempt.task_id == task.id)
        )
    )
    events = list(
        db.scalars(
            select(WorkflowEvent).where(WorkflowEvent.task_id == task.id)
        )
    )
    fence_events = [
        event
        for event in events
        if event.event_type == "execution_write_rejected"
        and event.error_code == "execution_fence_lost"
        and event.details == {"operation": "finish_execution"}
    ]
    calls = list(
        db.scalars(
            select(ModelCallRecord)
            .where(ModelCallRecord.task_id == task.id)
            .order_by(ModelCallRecord.id)
        )
    )
    cancellation_persisted = (
        task.status == "cancelled"
        and task.active_execution_id is None
        and any(attempt.status == "cancelled" for attempt in attempts)
    )
    rejected_attempt_ids = {
        event.execution_attempt_id for event in fence_events
    }
    replacement_result_preserved = (
        task.status == "completed"
        and task.active_execution_id is None
        and task.result_data is not None
        and task.result_summary is not None
        and any(
            attempt.status == "completed" and attempt.id not in rejected_attempt_ids
            for attempt in attempts
        )
    )
    fence_state = (
        "cancelled_without_result"
        if cancellation_persisted and task.result_data is None and task.result_summary is None
        else "replacement_result_preserved"
        if replacement_result_preserved
        else None
    )
    late_write_prevented = (
        fence_state is not None and bool(fence_events)
    )
    cost, cost_status = _model_cost_observation(calls)
    return EvaluationObservation(
        case_id=case_id,
        source="execution_fence",
        actual_outcome="cancelled" if fence_state == "cancelled_without_result" else "completed" if fence_state == "replacement_result_preserved" else "failed",
        model_calls=sum(call.charge_kind == "provider_model" for call in calls),
        provider_model_calls_by_node=dict(
            sorted(
                Counter(
                    call.node_name
                    for call in calls
                    if call.charge_kind == "provider_model"
                ).items()
            )
        ),
        local_resource_calls=sum(
            call.charge_kind == "local_resource" for call in calls
        ),
        tokens=sum(call.prompt_tokens + call.completion_tokens for call in calls),
        report_persisted=False,
        numeric_checks_passed=False,
        deterministic_validation_passed=False,
        security_check_status="passed" if late_write_prevented else "failed",
        execution_fence_status="passed" if fence_state is not None else "failed",
        late_execution_write_prevented_status=(
            "passed" if late_write_prevented else "failed"
        ),
        actual_execution_fence_codes=sorted(
            {
                event.error_code
                for event in fence_events
                if isinstance(event.error_code, str) and event.error_code
            }
        ),
        actual_execution_fence_state=fence_state,
        duration_ms=task.duration_ms,
        cost=cost,
        cost_status=cost_status,
    )
