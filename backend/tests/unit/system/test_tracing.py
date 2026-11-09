"""O1: one trace from request to model call, with allowlisted attributes only."""

import pytest
from app.core import tracing
from app.modules.workflow.orchestration.graph import _traced
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

QUESTION = "华东区2025年8月销售额是多少？客户 CUST-0001 的手机号 13800000000"


@pytest.fixture
def spans():
    exporter = InMemorySpanExporter()
    tracing.setup_tracing("test", processor=SimpleSpanProcessor(exporter))
    yield exporter
    exporter.clear()


def test_only_allowlisted_scalar_attributes_are_kept():
    assert tracing.safe_attributes(
        {
            "task_id": 7,
            "node": "data_node",
            "question": QUESTION,
            "sql": "SELECT 1",
            "gen_ai.request.model": "deepseek-chat",
            "tool.name": ["not", "scalar"],
            "company_id": None,
        }
    ) == {"task_id": 7, "node": "data_node", "gen_ai.request.model": "deepseek-chat"}


def test_worker_continues_the_trace_stored_on_the_task(spans):
    with tracing.span("http.request") as request_span:
        stored = tracing.current_traceparent()

    with tracing.span("analysis_task", traceparent=stored, attributes={"task_id": 1}):
        pass

    request, task = spans.get_finished_spans()
    assert stored is not None
    assert task.context.trace_id == request_span.get_span_context().trace_id
    assert task.parent is not None
    assert task.parent.span_id == request.context.span_id


def test_no_question_text_reaches_any_span(spans):
    class Gateway:
        model_name = "deepseek-chat"

        @tracing.traced_model_call("deepseek")
        def _chat_once(self, prompt, system_prompt=None):
            return "answer about " + prompt

    def planner_node(state):
        return {"answer": Gateway()._chat_once(state["question"], "system rules")}

    with tracing.span("analysis_task", attributes={"task_id": 3, "question": QUESTION}):
        result = _traced("planner_node", planner_node)({"question": QUESTION})

    assert result["answer"].endswith(QUESTION)
    finished = spans.get_finished_spans()
    assert [span.name for span in finished] == [
        "gen_ai.chat",
        "node.planner_node",
        "analysis_task",
    ]
    for span in finished:
        assert set(span.attributes or {}) <= tracing.ALLOWED_ATTRIBUTES
        for value in (span.attributes or {}).values():
            assert "华东" not in str(value) and "13800000000" not in str(value)


def test_failures_mark_the_span_with_the_error_class_only(spans):
    with pytest.raises(ValueError), tracing.span("node.data_node"):
        raise ValueError(QUESTION)

    (span,) = spans.get_finished_spans()
    assert span.attributes == {"error.class": "ValueError"}
    assert not span.events  # no exception message with the question in it


def test_api_request_span_uses_the_route_template(spans, monkeypatch):
    from app.main import app
    from fastapi.testclient import TestClient

    tracing.setup_tracing("test", processor=SimpleSpanProcessor(spans))
    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    (span,) = [s for s in spans.get_finished_spans() if s.name.startswith("GET")]
    assert span.name == "GET /health/live"
    assert span.attributes["http.response.status_code"] == 200


def test_collector_keeps_the_same_allowlist():
    import re
    from pathlib import Path

    config = (
        Path(__file__).resolve().parents[4] / "ops/observability/otel-collector.yml"
    ).read_text(encoding="utf-8")
    kept = re.search(r"keep_keys\(attributes, \[(.*?)\]\)", config, re.DOTALL)

    assert kept is not None
    assert set(re.findall(r'"([^"]+)"', kept.group(1))) == tracing.ALLOWED_ATTRIBUTES
