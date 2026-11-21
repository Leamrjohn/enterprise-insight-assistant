"""C3: every policy-built call leaves a manifest in the ledger, never the text."""

import json
from types import SimpleNamespace

from app.modules.reporting.semantic_review_service import SemanticReviewService
from app.modules.runtime import model_governance
from app.modules.runtime.context.manifest import content_hash
from app.modules.runtime.context_budget import (
    EVIDENCE_REVIEW,
    MAX_ROWS_WHEN_COMPRESSED,
    assemble,
    count_tokens,
)
from app.modules.runtime.model_governance import (
    model_call_scope,
    model_context_scope,
    reserve_model_call,
)
from app.modules.workflow.audit.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask

SECRET = "华东区内部口径"


def _sections() -> dict:
    rows = [["客户名称很长很长很长", i] for i in range(400)]
    return {
        "question": "本月销售额是多少？",
        "plan": {"route": "data_only", "reason": SECRET},
        "data_result": {"status": "ready", "evidence": [{"rows": rows}]},
        "not_declared": SECRET,
    }


def _by_name(manifest) -> dict:
    return {entry.name: entry for entry in manifest.sections}


def test_manifest_says_what_happened_to_each_section():
    sections = _sections()
    payload, decision = assemble(EVIDENCE_REVIEW, sections)
    manifest = decision.manifest
    entries = _by_name(manifest)

    assert manifest.policy == "evidence_review/1"
    assert manifest.estimated_tokens == decision.tokens == count_tokens(payload)
    assert [entry.name for entry in manifest.sections] == list(sections)
    assert entries["question"].action == "kept"
    assert entries["plan"].action == "filtered"
    assert entries["plan"].reason == "field_whitelist"
    assert entries["data_result"].action == "compressed"
    assert entries["not_declared"].action == "left_out"
    assert entries["not_declared"].final_tokens == 0
    assert entries["not_declared"].content_hash is None
    for name in ("question", "plan", "data_result"):
        entry = entries[name]
        assert entry.final_tokens == count_tokens(payload[name])
        assert entry.final_tokens <= entry.original_tokens
        assert entry.content_hash == content_hash(payload[name])
    rows_sent = payload["data_result"]["evidence"][0]["rows"]
    assert len(rows_sent) == MAX_ROWS_WHEN_COMPRESSED


def test_manifest_record_holds_counts_not_text():
    _, decision = assemble(EVIDENCE_REVIEW, _sections())
    record = decision.manifest.to_record()
    assert SECRET not in json.dumps(record, ensure_ascii=False)
    assert "本月销售额" not in json.dumps(record, ensure_ascii=False)
    assert record["over_budget"] is False


def test_over_budget_is_recorded_not_dropped():
    _, decision = assemble(EVIDENCE_REVIEW, {"question": "问" * 20000})
    assert decision.manifest.over_budget is True
    assert decision.manifest.to_record()["over_budget"] is True


def test_hash_ignores_key_order():
    assert content_hash({"a": 1, "b": "数"}) == content_hash({"b": "数", "a": 1})
    assert content_hash({"a": 1}) != content_hash({"a": 2})


# --- through the ledger --------------------------------------------------------


def _task(test_user) -> AnalysisTask:
    return AnalysisTask(
        user_id=test_user.id,
        question="c3 ledger",
        status="queued",
        stage="queued",
        model_budget_snapshot={
            "max_calls": 5,
            "max_calls_per_node": 5,
            "max_repairs": 1,
            "max_total_tokens": 1000,
            "max_cost": "1.00",
        },
        model_budget_usage={
            "calls": 0,
            "tokens": 0,
            "cost": "0.00",
            "reserved_cost": "0.00",
            "unknown_cost_calls": 0,
            "repairs": 0,
            "calls_by_node": {},
        },
    )


def test_every_call_in_the_scope_records_the_manifest(db_session, test_user):
    task = _task(test_user)
    db_session.add(task)
    db_session.commit()
    _, decision = assemble(EVIDENCE_REVIEW, _sections())

    with model_call_scope(
        db_session,
        task=task,
        attempt=SimpleNamespace(id=None),
        node_name="semantic_review",
    ):
        with model_context_scope(decision.manifest):
            reserve_model_call(provider="local", model_name="test-model")
            reserve_model_call(provider="local", model_name="test-model")  # repair
        reserve_model_call(provider="local", model_name="test-model")  # no policy

    first, repair, plain = (
        db_session.query(ModelCallRecord)
        .filter(ModelCallRecord.task_id == task.id)
        .order_by(ModelCallRecord.id)
        .all()
    )
    for record in (first, repair):
        assert record.context_policy == "evidence_review/1"
        assert record.context_manifest == decision.manifest.to_record()
    assert plain.context_policy is None and plain.context_manifest is None
    assert "context_tokens" in plain.resource_usage  # C2 counts stay
    assert SECRET not in json.dumps(first.context_manifest, ensure_ascii=False)


class _CapturingGateway:
    """Answers like a model and notes which manifest was in force per call."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.manifests = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False) -> str:
        self.manifests.append(model_governance._context_manifest.get())
        return self.responses.pop(0)

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_evidence_review_and_its_repair_carry_the_manifest():
    valid = json.dumps(
        {"verdict": "supported", "reason": "数据支持结论。", "limitations": []},
        ensure_ascii=False,
    )
    gateway = _CapturingGateway(["不是 JSON", valid])

    SemanticReviewService(gateway=gateway).review_evidence(
        question="本月销售额是多少？",
        plan={"action": "analyze", "route": "data_only"},
        data_result={"status": "ready", "evidence": [{"rows": [[1]]}]},
        knowledge_result={},
        report={"status": "completed"},
    )

    assert len(gateway.manifests) == 2  # first answer was repaired
    assert all(m is not None for m in gateway.manifests)
    # Shadow by default: /1 is sent, /2 recorded (C5d).
    assert {m.policy for m in gateway.manifests} == {"evidence_review/2:shadow"}
    assert model_governance._context_manifest.get() is None  # reset afterwards
