from datetime import datetime, timedelta, timezone

import pytest
from app.db.session import set_tenant_scope
from app.modules.documents.chunks import DocumentChunk
from app.modules.documents.models import Documents
from app.modules.evaluation.observation import (
    observation_from_duplicate_delivery,
    observation_from_execution_fence,
    observation_from_persisted_task,
    observation_from_runtime_tool_rejection,
    observation_from_sql_result_limit,
    observation_from_sql_timeout,
    observation_from_sql_validation_rejection,
)
from app.modules.organizations.models import Company
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.reviews.models import ReviewRequest
from app.modules.workflow.events_models import WorkflowEvent
from app.modules.workflow.execution_attempt import TaskExecutionAttempt
from app.modules.workflow.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask, AnalysisTaskDocument
from app.modules.workflow.tool_call import ToolCallRecord


def test_runtime_tool_rejection_observation_reads_denial_without_execution(
    db_session, test_user
) -> None:
    company = Company(name="runtime-tool-rejection-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="runtime tool denial",
        status="running",
        stage="retrieving_knowledge",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        ToolCallRecord(
            task_id=task.id,
            tool_name="rag_search",
            tool_contract_version="rag_search/v2",
            status="denied",
            error_code="tool_document_scope_denied",
            metadata_json={},
        )
    )
    db_session.flush()

    observation = observation_from_runtime_tool_rejection(
        db_session, case_id="runtime-document-scope-denial", task_id=task.id
    )

    assert observation.source == "runtime_tool_rejection"
    assert observation.actual_outcome == "failed"
    assert observation.runtime_tool_denial_status == "passed"
    assert observation.tool_execution_prevented_status == "passed"
    assert observation.actual_tool_denial_codes == ["tool_document_scope_denied"]
    assert observation.model_calls == 0
    assert observation.cost == "0.000000"


def test_sql_validation_rejection_observation_reads_failed_validation_without_result(
    db_session, test_user
) -> None:
    company = Company(name="sql-validation-rejection-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="reject evaluation schema",
        status="failed",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        ToolCallRecord(
            task_id=task.id,
            tool_name="sql_query",
            tool_contract_version="sql_query/v1",
            status="failed",
            error_code="sql_validation_error",
            metadata_json={},
        )
    )
    db_session.flush()

    observation = observation_from_sql_validation_rejection(
        db_session, case_id="sql-schema-injection", task_id=task.id
    )

    assert observation.source == "sql_validation_rejection"
    assert observation.actual_outcome == "failed"
    assert observation.sql_validation_rejection_status == "passed"
    assert observation.business_result_prevented_status == "passed"
    assert observation.actual_sql_validation_codes == ["sql_validation_error"]
    assert observation.model_calls == 0
    assert observation.cost == "0.000000"


def test_sql_timeout_observation_reads_a_timed_out_persisted_query(
    db_session, test_user
) -> None:
    company = Company(name="sql-timeout-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="timeout query",
        status="failed",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        ToolCallRecord(
            task_id=task.id,
            tool_name="sql_query",
            tool_contract_version="sql_query/v1",
            status="failed",
            error_code="sql_statement_timeout",
            metadata_json={},
        )
    )
    db_session.flush()

    observation = observation_from_sql_timeout(
        db_session, case_id="sql-statement-timeout", task_id=task.id
    )

    assert observation.source == "sql_timeout"
    assert observation.actual_outcome == "failed"
    assert observation.sql_timeout_status == "passed"
    assert observation.sql_timeout_result_prevented_status == "passed"
    assert observation.actual_sql_timeout_codes == ["sql_statement_timeout"]
    assert observation.model_calls == 0
    assert observation.cost == "0.000000"


def test_sql_result_limit_observation_reads_a_bounded_persisted_sql_call(
    db_session, test_user
) -> None:
    company = Company(name="sql-result-limit-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="bounded sql result",
        status="completed",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        ToolCallRecord(
            task_id=task.id,
            tool_name="sql_query",
            tool_contract_version="sql_query/v1",
            status="succeeded",
            metadata_json={"row_count": 1000, "result_status": "ready"},
        )
    )
    db_session.flush()

    observation = observation_from_sql_result_limit(
        db_session, case_id="sql-result-limit", task_id=task.id
    )

    assert observation.source == "sql_result_limit"
    assert observation.actual_outcome == "completed"
    assert observation.sql_result_limit_status == "passed"
    assert observation.actual_sql_result_row_count == 1000
    assert observation.model_calls == 0
    assert observation.cost == "0.000000"


def test_duplicate_delivery_observation_reads_rejected_claim_and_one_execution(
    db_session, test_user
) -> None:
    company = Company(name="duplicate-delivery-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="duplicate delivery",
        status="completed",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()
    attempt = TaskExecutionAttempt(
        task_id=task.id,
        execution_id="duplicate-delivery-test",
        status="completed",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    db_session.add(attempt)
    db_session.flush()
    db_session.add(
        WorkflowEvent(
            task_id=task.id,
            execution_attempt_id=attempt.id,
            company_id=company.id,
            sequence=0,
            event_type="execution_claim_rejected",
            node_name="claim_execution",
            status="rejected",
            error_code="execution_already_claimed",
            details={"operation": "claim_execution"},
        )
    )
    db_session.flush()

    observation = observation_from_duplicate_delivery(
        db_session, case_id="duplicate-delivery", task_id=task.id
    )

    assert observation.source == "duplicate_delivery"
    assert observation.actual_outcome == "completed"
    assert observation.duplicate_delivery_status == "passed"
    assert observation.duplicate_execution_prevented_status == "passed"
    assert observation.actual_duplicate_delivery_codes == ["execution_already_claimed"]
    assert observation.model_calls == 0


def test_execution_fence_observation_reads_cancelled_task_and_late_write_event(
    db_session, test_user
) -> None:
    company = Company(name="execution-fence-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="cancelled stale write",
        status="cancelled",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()
    attempt = TaskExecutionAttempt(
        task_id=task.id,
        execution_id="execution-fence-test",
        status="cancelled",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    db_session.add(attempt)
    db_session.flush()
    db_session.add(
        WorkflowEvent(
            task_id=task.id,
            execution_attempt_id=attempt.id,
            company_id=company.id,
            sequence=0,
            event_type="execution_write_rejected",
            node_name="saving_result",
            status="rejected",
            error_code="execution_fence_lost",
            details={"operation": "finish_execution"},
        )
    )
    db_session.flush()

    observation = observation_from_execution_fence(
        db_session, case_id="cancelled-stale-write", task_id=task.id
    )

    assert observation.source == "execution_fence"
    assert observation.actual_outcome == "cancelled"
    assert observation.execution_fence_status == "passed"
    assert observation.late_execution_write_prevented_status == "passed"
    assert observation.actual_execution_fence_codes == ["execution_fence_lost"]
    assert observation.actual_execution_fence_state == "cancelled_without_result"


def test_execution_fence_observation_reads_preserved_replacement_result(
    db_session, test_user
) -> None:
    company = Company(name="execution-fence-replacement-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="replacement stale write",
        status="completed",
        stage="completed",
        result_summary="fresh",
        result_data={"state": "fresh"},
    )
    db_session.add(task)
    db_session.flush()
    old = TaskExecutionAttempt(
        task_id=task.id,
        execution_id="execution-fence-old",
        status="expired",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    replacement = TaskExecutionAttempt(
        task_id=task.id,
        execution_id="execution-fence-new",
        status="completed",
        lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    db_session.add_all([old, replacement])
    db_session.flush()
    db_session.add(
        WorkflowEvent(
            task_id=task.id,
            execution_attempt_id=old.id,
            company_id=company.id,
            sequence=0,
            event_type="execution_write_rejected",
            node_name="saving_result",
            status="rejected",
            error_code="execution_fence_lost",
            details={"operation": "finish_execution"},
        )
    )
    db_session.flush()

    observation = observation_from_execution_fence(
        db_session, case_id="replacement-stale-write", task_id=task.id
    )

    assert observation.actual_outcome == "completed"
    assert observation.execution_fence_status == "passed"
    assert observation.late_execution_write_prevented_status == "passed"
    assert observation.actual_execution_fence_state == "replacement_result_preserved"


def test_observation_reads_only_persisted_terminal_task_facts(
    db_session, test_user
) -> None:
    report = FinalAnalysisReport(
        status="completed",
        executive_summary="华东销售下降。",
        confirmed_facts=[
            {
                "fact_id": "fact-east-sales",
                "statement": "华东销售额下降",
                "data_evidence_ids": ["sales-comparison"],
            }
        ],
        hypotheses=[
            {
                "hypothesis_id": "hypothesis-contract",
                "statement": "客户合同到期后暂停采购",
                "related_fact_ids": ["fact-east-sales"],
                "citation_chunk_ids": [101],
                "support_level": "high",
            }
        ],
        data_evidence=[{"evidence_id": "sales-comparison", "purpose": "环比销售额"}],
        document_citations=[{"chunk_id": 101, "excerpt": "合同到期后暂停采购。"}],
        recommendations=[
            {
                "recommendation_id": "recommendation-1",
                "priority": "medium",
                "action": "建立下钻核验清单。",
                "rationale": "基于已确认销售事实。",
                "basis_fact_ids": ["fact-east-sales"],
            }
        ],
    )
    task = AnalysisTask(
        user_id=test_user.id,
        question="华东销售为何下降？",
        status="completed",
        stage="completed",
        duration_ms=600,
        result_data={
            "plan": {"route": "hybrid", "intent": {"kind": "business_cause"}},
            "knowledge_result": {
                "status": "ready",
                "evidences": [{"chunk_id": 101}],
            },
            "review_result": {
                "semantic_review": {"verdict": "supported"},
                "citation_chunk_ids": [101],
            },
            "report": report.model_dump(mode="json"),
            "deterministic_validation": {
                "status": "passed",
                "checks": {
                    "schema_valid": True,
                    "numbers_valid": True,
                    "citations_valid": True,
                    "report_validated": True,
                },
            },
        },
    )
    db_session.add(task)
    db_session.flush()
    db_session.add_all(
        [
            ModelCallRecord(
                task_id=task.id,
                node_name="planner",
                provider="test",
                model_name="test-model",
                billing_status="settled",
                prompt_tokens=11,
                completion_tokens=7,
                cost=0.01,
                duration_ms=10,
                result_category="success",
            ),
            ModelCallRecord(
                task_id=task.id,
                node_name="reviewer",
                provider="test",
                model_name="test-model",
                billing_status="settled",
                prompt_tokens=13,
                completion_tokens=9,
                cost=0.02,
                duration_ms=12,
                result_category="success",
            ),
            ModelCallRecord(
                task_id=task.id,
                node_name="knowledge",
                provider="local",
                model_name="test-reranker",
                charge_kind="local_resource",
                billing_status="settled",
                prompt_tokens=0,
                completion_tokens=0,
                cost=0,
                duration_ms=8,
                result_category="success",
            ),
        ]
    )
    db_session.flush()

    observation = observation_from_persisted_task(
        db_session, case_id="sales-decline-east-normal", task_id=task.id
    )

    assert observation.actual_route == "hybrid"
    assert observation.actual_plan_intent_kind == "business_cause"
    assert observation.knowledge_result_status == "ready"
    assert observation.knowledge_evidence_count == 1
    assert observation.semantic_review_verdict == "supported"
    assert observation.reviewer_citation_chunk_count == 1
    assert observation.actual_confirmed_facts == ["华东销售额下降"]
    assert observation.actual_supported_claims == ["客户合同到期后暂停采购"]
    assert observation.actual_recommendation_actions == ["建立下钻核验清单。"]
    assert observation.returned_chunk_ids == [101]
    assert observation.actual_outcome == "completed"
    assert observation.model_calls == 2
    assert observation.provider_model_calls_by_node == {
        "planner": 1,
        "reviewer": 1,
    }
    assert observation.local_resource_calls == 1
    assert observation.tokens == 40
    assert observation.cost == "0.030000"
    assert observation.cost_status == "passed"
    assert observation.report_persisted
    assert observation.numeric_checks_passed
    assert observation.numeric_check_status == "passed"
    assert observation.deterministic_validation_passed
    assert observation.deterministic_validation_status == "passed"
    assert observation.security_check_status == "unknown"
    assert observation.citation_validation_status == "passed"


def test_observation_rejects_non_terminal_task(db_session, test_user) -> None:
    task = AnalysisTask(
        user_id=test_user.id, question="仍在运行", status="running", stage="planning"
    )
    db_session.add(task)
    db_session.flush()

    try:
        observation_from_persisted_task(db_session, case_id="running", task_id=task.id)
    except ValueError as error:
        assert "not in an evaluable terminal state" in str(error)
    else:
        raise AssertionError("non-terminal task must not become an observation")


def test_observation_separates_worker_execution_from_human_review_wait(
    db_session, test_user
) -> None:
    company = Company(name="timing-observation-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="timing observation",
        status="completed",
        stage="completed",
        duration_ms=70000,
    )
    db_session.add(task)
    db_session.flush()
    started_at = datetime(2026, 10, 19, tzinfo=timezone.utc)
    db_session.add_all(
        [
            TaskExecutionAttempt(
                task_id=task.id,
                execution_id="timing-observation-analysis",
                status="completed",
                lease_expires_at=started_at + timedelta(minutes=1),
                started_at=started_at,
                finished_at=started_at + timedelta(seconds=12),
            ),
            TaskExecutionAttempt(
                task_id=task.id,
                execution_id="timing-observation-publish",
                status="completed",
                lease_expires_at=started_at + timedelta(minutes=2),
                started_at=started_at + timedelta(seconds=66),
                finished_at=started_at + timedelta(seconds=68),
            ),
        ]
    )
    db_session.add(
        ReviewRequest(
            task_id=task.id,
            company_id=company.id,
            status="approved",
            reason_code="causal_hypothesis_requires_human_review",
            created_at=started_at + timedelta(seconds=12),
            reviewed_at=started_at + timedelta(seconds=65),
        )
    )
    db_session.flush()

    observation = observation_from_persisted_task(
        db_session, case_id="timing-observation", task_id=task.id
    )

    assert observation.duration_ms == 70000
    assert observation.machine_execution_duration_ms == 14000
    assert observation.human_review_wait_ms == 53000


def test_observation_preserves_needs_clarification_as_a_terminal_outcome(
    db_session, test_user
) -> None:
    task = AnalysisTask(
        user_id=test_user.id,
        question="请分析最近经营情况",
        status="needs_clarification",
        stage="completed",
        clarification_status="waiting",
        clarification_missing_fields=["time_range", "region"],
    )
    db_session.add(task)
    db_session.flush()

    observation = observation_from_persisted_task(
        db_session, case_id="clarification", task_id=task.id
    )

    assert observation.actual_outcome == "needs_clarification"
    assert observation.actual_clarification_missing_fields == ["time_range", "region"]
    assert observation.no_side_effects_status == "passed"
    assert observation.security_check_status == "passed"


def test_observation_reads_insufficient_evidence_from_workflow_outcome(
    db_session, test_user
) -> None:
    task = AnalysisTask(
        user_id=test_user.id,
        question="请列出资料支持SUP-003传感器批次异常的依据。",
        status="partial",
        stage="completed",
        result_data={
            "terminal_result": {
                "outcome": "insufficient_evidence",
                "reason": "knowledge_insufficient",
            }
        },
    )
    db_session.add(task)
    db_session.flush()

    observation = observation_from_persisted_task(
        db_session, case_id="development-empty-document-evidence", task_id=task.id
    )

    assert observation.actual_outcome == "insufficient_evidence"


def test_observation_does_not_total_unknown_model_charges(
    db_session, test_user
) -> None:
    task = AnalysisTask(
        user_id=test_user.id,
        question="费用状态必须保留",
        status="failed",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add_all(
        [
            ModelCallRecord(
                task_id=task.id,
                node_name="planner",
                provider="test",
                model_name="settled-model",
                billing_status="settled",
                cost=0.01,
                result_category="success",
            ),
            ModelCallRecord(
                task_id=task.id,
                node_name="reviewer",
                provider="test",
                model_name="unknown-model",
                billing_status="unknown",
                cost=None,
                result_category="retryable_error",
            ),
        ]
    )
    db_session.flush()

    observation = observation_from_persisted_task(
        db_session, case_id="unknown-cost", task_id=task.id
    )

    assert observation.cost is None
    assert observation.cost_status == "unknown"


def test_observation_marks_a_zero_call_task_as_known_zero_cost(
    db_session, test_user
) -> None:
    task = AnalysisTask(
        user_id=test_user.id,
        question="拒绝请求无需模型",
        status="failed",
        stage="completed",
    )
    db_session.add(task)
    db_session.flush()

    observation = observation_from_persisted_task(
        db_session, case_id="zero-call-cost", task_id=task.id
    )

    assert observation.model_calls == 0
    assert observation.cost == "0.000000"
    assert observation.cost_status == "passed"


@pytest.mark.parametrize(
    ("file_path", "source"),
    [
        ("events/east-sales-review.md", "test"),
        (None, "events/east-sales-review.md"),
    ],
)
def test_observation_reads_all_evaluation_fields_and_rechecks_frozen_scope(
    db_session, test_user, file_path, source
) -> None:
    company = Company(name="evaluation-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    document = Documents(
        uploaded_by_user_id=test_user.id,
        company_id=company.id,
        name="evaluation-source",
        source=source,
        file_path=file_path,
        status="completed",
    )
    db_session.add(document)
    db_session.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        company_id=company.id,
        chunk_index=0,
        content="合同到期后暂停采购。",
        token_count=3,
    )
    db_session.add(chunk)
    db_session.flush()
    report = FinalAnalysisReport(
        status="completed",
        executive_summary="华东销售下降。",
        confirmed_facts=[
            {
                "fact_id": "fact-east-sales",
                "statement": "华东销售额下降",
                "data_evidence_ids": ["sales-comparison"],
            }
        ],
        data_evidence=[{"evidence_id": "sales-comparison", "purpose": "环比销售额"}],
        document_citations=[
            {
                "chunk_id": chunk.id,
                "document_id": document.id,
                "excerpt": "合同到期后暂停采购。",
            }
        ],
    )
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="华东销售为何下降？",
        status="completed",
        stage="completed",
        result_data={
            "plan": {"route": "hybrid"},
            "evaluation_facts": {
                "entities": ["华东", "CUST-0001"],
                "period": "2025-08 compared_to 2025-07",
                "data_status": "insufficient_evidence",
                "data_error_code": "no_matching_records",
                "result_fingerprint": {"algorithm": "sha256", "value": "a" * 64},
                "semantic_result_fingerprint": {
                    "algorithm": "sha256",
                    "value": "b" * 64,
                },
            },
            "report": report.model_dump(mode="json"),
        },
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(AnalysisTaskDocument(task_id=task.id, document_id=document.id))
    db_session.flush()

    observation = observation_from_persisted_task(
        db_session, case_id="complete-fields", task_id=task.id
    )

    assert observation.actual_entities == ["华东", "CUST-0001"]
    assert observation.actual_period == "2025-08 compared_to 2025-07"
    assert observation.actual_data_status == "insufficient_evidence"
    assert observation.actual_data_error_code == "no_matching_records"
    assert observation.actual_result_fingerprint == {
        "algorithm": "sha256",
        "value": "a" * 64,
    }
    assert observation.actual_semantic_result_fingerprint == {
        "algorithm": "sha256",
        "value": "b" * 64,
    }
    assert observation.returned_document_paths == ["events/east-sales-review.md"]
    assert observation.security_check_status == "passed"


def test_observation_fails_when_report_cites_chunk_outside_frozen_scope(
    db_session, test_user
) -> None:
    company = Company(name="evaluation-security-company")
    db_session.add(company)
    db_session.flush()
    set_tenant_scope(db_session, company.id)
    frozen_document = Documents(
        uploaded_by_user_id=test_user.id,
        company_id=company.id,
        name="frozen",
        source="test",
        file_path="allowed.md",
        status="completed",
    )
    cited_document = Documents(
        uploaded_by_user_id=test_user.id,
        company_id=company.id,
        name="outside-frozen-scope",
        source="test",
        file_path="outside.md",
        status="completed",
    )
    db_session.add_all([frozen_document, cited_document])
    db_session.flush()
    cited_chunk = DocumentChunk(
        document_id=cited_document.id,
        company_id=company.id,
        chunk_index=0,
        content="范围外内容。",
        token_count=3,
    )
    db_session.add(cited_chunk)
    db_session.flush()
    report = FinalAnalysisReport(
        status="completed",
        executive_summary="测试报告。",
        confirmed_facts=[
            {
                "fact_id": "test-fact",
                "statement": "测试事实。",
                "data_evidence_ids": ["test-evidence"],
            }
        ],
        data_evidence=[{"evidence_id": "test-evidence", "purpose": "测试"}],
        document_citations=[
            {
                "chunk_id": cited_chunk.id,
                "document_id": cited_document.id,
                "excerpt": "范围外内容。",
            }
        ],
    )
    task = AnalysisTask(
        user_id=test_user.id,
        company_id=company.id,
        question="范围测试",
        status="completed",
        stage="completed",
        result_data={"report": report.model_dump(mode="json")},
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        AnalysisTaskDocument(task_id=task.id, document_id=frozen_document.id)
    )
    db_session.flush()

    observation = observation_from_persisted_task(
        db_session, case_id="outside-frozen-scope", task_id=task.id
    )

    assert observation.returned_document_paths == ["outside.md"]
    assert observation.security_check_status == "failed"


@pytest.mark.parametrize(
    (
        "checks",
        "validation_status",
        "expected_citation_status",
        "expected_numeric_status",
        "expected_validation_status",
    ),
    [
        ({"citations_valid": False}, None, "failed", "unknown", "unknown"),
        ({}, "unknown", "unknown", "unknown", "unknown"),
        ({"numbers_valid": False}, "failed", "unknown", "failed", "failed"),
    ],
)
def test_observation_preserves_validation_statuses(
    db_session,
    test_user,
    checks,
    validation_status,
    expected_citation_status,
    expected_numeric_status,
    expected_validation_status,
) -> None:
    validation = {"checks": checks}
    if validation_status is not None:
        validation["status"] = validation_status
    task = AnalysisTask(
        user_id=test_user.id,
        question="引用校验状态",
        status="completed",
        stage="completed",
        result_data={"deterministic_validation": validation},
    )
    db_session.add(task)
    db_session.flush()

    observation = observation_from_persisted_task(
        db_session, case_id="citation-validation", task_id=task.id
    )

    assert observation.citation_validation_status == expected_citation_status
    assert observation.numeric_check_status == expected_numeric_status
    assert observation.deterministic_validation_status == expected_validation_status
