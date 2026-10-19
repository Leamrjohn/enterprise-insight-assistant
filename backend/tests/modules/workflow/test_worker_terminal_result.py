from datetime import datetime, timezone

import app.modules.workflow.tasks as analysis_tasks
from app.modules.reporting.schemas import FinalAnalysisReport
from app.modules.workflow.schemas import TaskOut


class FakeDb:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, record) -> None:
        return None


class FakeTaskRecord:
    def __init__(self) -> None:
        self.id = 1
        self.user_id = 10
        self.document_id = None
        self.question = "写一首诗"
        self.status = "running"
        self.stage = "call_model"
        self.attempt_count = 1
        self.result_summary = None
        self.result_data = None
        self.error_message = None
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    @property
    def report(self):
        if not isinstance(self.result_data, dict):
            return None
        return self.result_data.get("report")


class FakeAttempt:
    def __init__(self, record: FakeTaskRecord) -> None:
        self.record = record


class FakeExecution:
    def __init__(self, record: FakeTaskRecord) -> None:
        self.attempt = FakeAttempt(record)


def _save(db, record: FakeTaskRecord, workflow_result: dict, monkeypatch) -> None:
    monkeypatch.setattr(
        analysis_tasks, "checkpoint_stage", lambda *args, **kwargs: True
    )

    def fake_finish(
        db,
        *,
        attempt,
        task_status,
        result_summary,
        result_data,
        error_message,
        **kwargs,
    ):
        task = attempt.record
        task.status = task_status
        task.stage = "completed"
        task.result_summary = result_summary
        task.result_data = result_data
        task.error_message = error_message
        return True

    monkeypatch.setattr(analysis_tasks, "finish_execution", fake_finish)
    analysis_tasks._save_workflow_result(
        db, record, FakeExecution(record), workflow_result
    )


def test_worker_saves_langgraph_terminal_result(monkeypatch) -> None:
    db = FakeDb()
    record = FakeTaskRecord()
    workflow_result = {
        "plan": {
            "action": "scope_exit",
            "route": None,
            "reason": "与经营分析无关",
        },
        "terminal_result": {
            "outcome": "scope_exit",
            "reason": "与经营分析无关",
        },
        "final_answer": "我目前只处理经营数据和内部资料分析。",
        "planner_result": {
            "status": "ready",
            "attempts": {"model_attempts": 2},
        },
        "data_result": None,
        "knowledge_result": None,
        "review_result": None,
        "report": None,
        "execution": {
            "external_retry_count": 0,
            "max_external_retries": 0,
            "loop_stop_reason": None,
            "loop_history": [],
            "scope_fingerprint": None,
        },
    }

    _save(db, record, workflow_result, monkeypatch)

    assert db.commits == 1
    assert record.status == "completed"
    assert record.stage == "completed"
    assert record.result_summary == "我目前只处理经营数据和内部资料分析。"
    assert record.error_message is None
    assert record.result_data == {
        "type": "langgraph_workflow",
        "answer": "我目前只处理经营数据和内部资料分析。",
        "plan": workflow_result["plan"],
        "planner_result": workflow_result["planner_result"],
        "terminal_result": workflow_result["terminal_result"],
        "data_result": None,
        "knowledge_result": None,
        "review_result": None,
        "report": None,
        "publication": {
            "decision": "not_applicable",
            "report_location": "none",
            "reason_code": "direct_response",
        },
        "evaluation_facts": {
            "entities": None,
            "period": None,
            "data_status": None,
            "data_error_code": None,
            "result_fingerprint": None,
            "semantic_result_fingerprint": None,
        },
        "execution": {
            "external_retry_count": 0,
            "max_external_retries": 0,
            "loop_stop_reason": None,
            "loop_history": [],
            "scope_fingerprint": None,
        },
    }


def test_worker_persists_evaluation_facts_from_plan_and_validated_data(
    monkeypatch,
) -> None:
    db = FakeDb()
    record = FakeTaskRecord()
    workflow_result = {
        "plan": {
            "action": "analyze",
            "route": "data_only",
            "evaluation_scope": {
                "entities": ["华东", "CUST-0001"],
                "period": "2025-08 compared_to 2025-07",
            },
        },
        "terminal_result": None,
        "final_answer": "已完成。",
        "data_result": {
            "status": "ready",
            "evidence": [
                {
                    "columns": ["region", "sales"],
                    "rows": [["EAST", "100"]],
                }
            ],
        },
        "knowledge_result": None,
        "review_result": {"review_status": "completed"},
    }

    _save(db, record, workflow_result, monkeypatch)

    assert record.result_data["evaluation_facts"] == {
        "entities": ["华东", "CUST-0001"],
        "period": "2025-08 compared_to 2025-07",
        "data_status": "ready",
        "data_error_code": None,
        "result_fingerprint": {
            "algorithm": "sha256",
            "value": "9982d064b3a28d3d5da44b0e1ed99ff684a1cfd085b1970339f4b66d543de4f1",
        },
        "semantic_result_fingerprint": None,
    }


def test_explicitly_empty_document_scope_returns_no_allowed_chunks(monkeypatch) -> None:
    class _EmptyQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return []

    class _Db:
        def query(self, *_args, **_kwargs):
            return _EmptyQuery()

    assert analysis_tasks._frozen_allowed_chunk_ids(_Db(), task_id=1) == set()


def test_worker_marks_planner_failure_as_failed(monkeypatch) -> None:
    db = FakeDb()
    record = FakeTaskRecord()
    workflow_result = {
        "plan": None,
        "planner_result": {
            "status": "failed",
            "attempts": {"model_attempts": 2},
        },
        "terminal_result": {
            "outcome": "failed",
            "stage": "planning",
            "error_code": "planner_invalid_output",
            "retryable": False,
        },
        "final_answer": "本次分析暂未完成，请稍后重试。",
        "data_result": None,
        "knowledge_result": None,
        "review_result": None,
    }

    _save(db, record, workflow_result, monkeypatch)

    assert record.status == "failed"
    assert record.stage == "completed"
    assert record.error_message == "分析工作流未能生成可返回的结果。"
    assert record.result_data["planner_result"] == workflow_result["planner_result"]


def test_worker_marks_partial_review_as_partial(monkeypatch) -> None:
    db = FakeDb()
    record = FakeTaskRecord()
    workflow_result = {
        "plan": {
            "action": "analyze",
            "route": "hybrid",
            "reason": "需要数据和资料。",
        },
        "terminal_result": None,
        "final_answer": "销售额已下降，但现有资料不足以确认原因。",
        "data_result": {
            "status": "ready",
            "evidence": [],
        },
        "knowledge_result": {
            "status": "insufficient_evidence",
            "answer": "无法回答：资料不足",
            "evidences": [],
        },
        "review_result": {
            "review_status": "partial",
            "data_available": True,
            "knowledge_available": False,
            "limitations": ["未检索到足够的文档证据。"],
        },
    }

    _save(db, record, workflow_result, monkeypatch)

    assert record.status == "partial"
    assert record.stage == "completed"
    assert record.error_message is None
    assert record.result_summary == "销售额已下降，但现有资料不足以确认原因。"
    assert record.result_data["review_result"]["review_status"] == "partial"


def test_task_response_schema_accepts_langgraph_result_data() -> None:
    record = FakeTaskRecord()
    record.status = "completed"
    record.stage = "completed"
    record.result_summary = "我目前只处理经营数据和内部资料分析。"
    record.result_data = {
        "type": "langgraph_workflow",
        "answer": record.result_summary,
        "plan": {"action": "scope_exit"},
        "planner_result": {
            "status": "ready",
            "attempts": {"model_attempts": 1},
        },
        "terminal_result": {"outcome": "scope_exit"},
        "data_result": None,
        "knowledge_result": None,
        "review_result": None,
    }

    payload = TaskOut.model_validate(record).model_dump(mode="json")

    assert payload["result_data"] == record.result_data
    assert payload["report"] is None


def test_worker_promotes_validated_report_to_task_response(monkeypatch) -> None:
    db = FakeDb()
    record = FakeTaskRecord()
    report = {
        "schema_version": "1.0",
        "status": "completed",
        "executive_summary": "已确认经营数据事实；文档提供了待进一步核验的可能原因。",
        "confirmed_facts": [
            {
                "fact_id": "fact-1",
                "statement": "华东区销售额下降。",
                "data_evidence_ids": ["data-1"],
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis-1",
                "statement": "可能原因（未证实）：客户下调采购计划。",
                "related_fact_ids": ["fact-1"],
                "citation_chunk_ids": [9],
                "support_level": "low",
            }
        ],
        "recommendations": [
            {
                "recommendation_id": "recommendation-1",
                "priority": "medium",
                "action": "核验订单和交付状态。",
                "rationale": "基于已确认数据和文档线索。",
                "basis_fact_ids": ["fact-1"],
                "basis_hypothesis_ids": ["hypothesis-1"],
            }
        ],
        "data_evidence": [
            {
                "evidence_id": "data-1",
                "purpose": "月度销售额比较",
                "columns": ["month", "total_sales"],
                "rows": [["2025-08", "1847604.72"]],
            }
        ],
        "document_citations": [
            {"chunk_id": 9, "document_id": 4, "excerpt": "客户下调采购计划。"}
        ],
        "limitations": [],
    }
    workflow_result = {
        "final_answer": "销售额下降，可能与客户下调采购计划有关。",
        "review_result": {
            "review_status": "complete",
            "report": report,
            "answer_validation": {
                "schema_valid": True,
                "numbers_valid": True,
                "citations_valid": True,
            },
        },
    }

    _save(db, record, workflow_result, monkeypatch)

    payload = TaskOut.model_validate(record).model_dump(mode="json")
    expected_report = FinalAnalysisReport.model_validate(report).model_dump(mode="json")
    assert record.result_data["report"] == expected_report
    assert record.result_data["deterministic_validation"] == {
        "status": "passed",
        "checks": {
            "schema_valid": True,
            "numbers_valid": True,
            "citations_valid": True,
            "report_validated": True,
        },
    }
    assert payload["report"] == expected_report


def test_deterministic_validation_keeps_missing_or_failed_checks_visible() -> None:
    assert analysis_tasks._deterministic_validation_result({}, None)["status"] == "unknown"
    assert (
        analysis_tasks._deterministic_validation_result(
            {"answer_validation": {"numbers_valid": False}}, True
        )["status"]
        == "failed"
    )


def test_worker_holds_company_scoped_causal_report_for_human_review(
    monkeypatch,
) -> None:
    db = FakeDb()
    record = FakeTaskRecord()
    record.company_id = 3
    created = []
    monkeypatch.setattr(
        analysis_tasks,
        "create_review_request",
        lambda _db, *, task: created.append(task.id),
    )
    report = {
        "status": "completed",
        "executive_summary": "经营数据确认下降，原因仍需人工复核。",
        "confirmed_facts": [
            {
                "fact_id": "fact-1",
                "statement": "销售额下降。",
                "data_evidence_ids": ["data-1"],
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis-1",
                "statement": "可能原因（未证实）：客户缩减采购。",
                "related_fact_ids": ["fact-1"],
                "citation_chunk_ids": [8],
                "support_level": "low",
            }
        ],
        "recommendations": [
            {
                "recommendation_id": "recommendation-1",
                "priority": "medium",
                "action": "复核客户计划。",
                "rationale": "基于已确认事实和待审核假设。",
                "basis_fact_ids": ["fact-1"],
            }
        ],
        "data_evidence": [
            {
                "evidence_id": "data-1",
                "purpose": "销售比较",
                "columns": ["sales"],
                "rows": [[1]],
            }
        ],
        "document_citations": [{"chunk_id": 8, "excerpt": "客户缩减采购计划。"}],
        "limitations": [],
    }

    _save(
        db,
        record,
        {
            "final_answer": "待审核结论。",
            "review_result": {"review_status": "complete", "report": report},
        },
        monkeypatch,
    )

    assert record.status == "awaiting_review"
    assert record.report is None
    assert record.result_data["report_draft"]["status"] == "completed"
    assert record.result_data["review"]["status"] == "pending"
    assert record.result_data["publication"]["decision"] == "awaiting_human_review"
    assert created == [record.id]


def test_worker_marks_retryable_planner_failure_as_failed(monkeypatch) -> None:
    db = FakeDb()
    record = FakeTaskRecord()
    workflow_result = {
        "plan": None,
        "terminal_result": {
            "outcome": "failed",
            "stage": "planning",
            "error_code": "planner_model_retryable_error",
            "retryable": True,
        },
        "final_answer": "本次分析暂未完成，请稍后重试。",
        "data_result": None,
        "knowledge_result": None,
        "review_result": None,
    }

    _save(db, record, workflow_result, monkeypatch)

    assert record.status == "failed"
    assert record.stage == "completed"


def test_worker_serializes_datetime_values_before_persisting_result_data(
    monkeypatch,
) -> None:
    db = FakeDb()
    record = FakeTaskRecord()
    workflow_result = {
        "plan": {"action": "analyze", "route": "data_only"},
        "terminal_result": None,
        "final_answer": "已完成。",
        "data_result": {
            "status": "ready",
            "evidence": [{"rows": [[datetime(2025, 8, 1, tzinfo=timezone.utc)]]}],
        },
        "knowledge_result": None,
        "review_result": {"review_status": "completed"},
    }

    _save(db, record, workflow_result, monkeypatch)

    assert record.result_data["data_result"]["evidence"][0]["rows"][0][0] == (
        "2025-08-01T00:00:00+00:00"
    )
