from datetime import datetime, timezone

import app.tasks.analysis_tasks as analysis_tasks
from app.schemas.task import TaskOut


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


def test_worker_saves_langgraph_terminal_result() -> None:
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
    }

    analysis_tasks._save_workflow_result(db, record, workflow_result)

    assert db.commits == 2
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
    }


def test_worker_marks_planner_failure_as_failed() -> None:
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

    analysis_tasks._save_workflow_result(db, record, workflow_result)

    assert record.status == "failed"
    assert record.stage == "completed"
    assert record.error_message == "分析工作流未能生成可返回的结果。"
    assert record.result_data["planner_result"] == workflow_result["planner_result"]


def test_worker_marks_partial_review_as_partial() -> None:
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

    analysis_tasks._save_workflow_result(db, record, workflow_result)

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


def test_worker_marks_retryable_planner_failure_as_failed() -> None:
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

    analysis_tasks._save_workflow_result(db, record, workflow_result)

    assert record.status == "failed"
    assert record.stage == "completed"
