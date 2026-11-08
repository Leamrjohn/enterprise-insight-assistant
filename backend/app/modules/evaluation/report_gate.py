"""Deterministic report-gate evaluation: tampered variants must be blocked, controls kept.

Covers the two code gates on the publish path: ``validate_report`` (schema links and
frozen citation scope) and ``validate_numbers`` (every displayed number must exist in
the controlled SQL rows or cited text).  No model is involved.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass

from app.modules.reporting.numeric_validation import validate_numbers
from app.modules.reporting.validation import ReportValidationError, validate_report

ALLOWED_CHUNK_IDS = frozenset({8})


def base_report() -> dict:
    return {
        "status": "partial",
        "executive_summary": "发现销售下降。",
        "confirmed_facts": [
            {
                "fact_id": "fact-1",
                "statement": "销售下降。",
                "data_evidence_ids": ["data-1"],
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis-1",
                "statement": "价格调整可能影响销量。",
                "related_fact_ids": ["fact-1"],
                "citation_chunk_ids": [8],
                "support_level": "low",
            }
        ],
        "recommendations": [
            {
                "recommendation_id": "rec-1",
                "priority": "medium",
                "action": "复核华东区价格策略。",
                "rationale": "销量下降与价格调整同期出现。",
                "basis_fact_ids": ["fact-1"],
                "basis_hypothesis_ids": ["hypothesis-1"],
            }
        ],
        "data_evidence": [{"evidence_id": "data-1", "purpose": "固定查询"}],
        "document_citations": [{"chunk_id": 8, "excerpt": "价格调整通知。"}],
        "limitations": [
            {"code": "partial", "message": "资料有限。", "next_step": "补充资料。"}
        ],
    }


def _mutate(change: Callable[[dict], object]) -> dict:
    report = base_report()
    change(report)
    return report


# Each variant breaks exactly one rule a published report must satisfy.
REPORT_TAMPERS: dict[str, Callable[[], dict]] = {
    "fact_without_data_evidence": lambda: _mutate(
        lambda r: r["confirmed_facts"][0].update(data_evidence_ids=[])
    ),
    "fact_cites_missing_evidence": lambda: _mutate(
        lambda r: r["confirmed_facts"][0].update(data_evidence_ids=["data-404"])
    ),
    "hypothesis_without_citation": lambda: _mutate(
        lambda r: r["hypotheses"][0].update(citation_chunk_ids=[])
    ),
    "hypothesis_cites_missing_chunk": lambda: _mutate(
        lambda r: r["hypotheses"][0].update(citation_chunk_ids=[99])
    ),
    "hypothesis_links_missing_fact": lambda: _mutate(
        lambda r: r["hypotheses"][0].update(related_fact_ids=["fact-404"])
    ),
    "recommendation_links_missing_fact": lambda: _mutate(
        lambda r: r["recommendations"][0].update(basis_fact_ids=["fact-404"])
    ),
    "recommendation_without_basis": lambda: _mutate(
        lambda r: r["recommendations"][0].update(
            basis_fact_ids=[], basis_hypothesis_ids=[]
        )
    ),
    "completed_with_limitations": lambda: _mutate(
        lambda r: r.update(status="completed")
    ),
    "partial_without_limitations": lambda: _mutate(lambda r: r.update(limitations=[])),
    "failed_with_conclusions": lambda: _mutate(lambda r: r.update(status="failed")),
    "citation_outside_frozen_scope": lambda: _mutate(
        lambda r: (
            r["document_citations"][0].update(chunk_id=9),
            r["hypotheses"][0].update(citation_chunk_ids=[9]),
        )
    ),
}

# A tamper only counts as intercepted when the intended rule fired, not an
# unrelated schema error introduced by a sloppy sample.
EXPECTED_REASONS = {
    "fact_without_data_evidence": "at least 1 item",
    "fact_cites_missing_evidence": "事实必须关联已有数据证据",
    "hypothesis_without_citation": "假设必须关联至少一条文档或附件引用",
    "hypothesis_cites_missing_chunk": "假设必须关联已有文档引用",
    "hypothesis_links_missing_fact": "假设必须关联已有确认事实",
    "recommendation_links_missing_fact": "建议关联了不存在的事实",
    "recommendation_without_basis": "建议必须关联至少一条事实或假设",
    "completed_with_limitations": "completed 状态不能包含限制",
    "partial_without_limitations": "partial 状态必须说明资料或执行限制",
    "failed_with_conclusions": "failed 状态不能包含分析结论",
    "citation_outside_frozen_scope": "frozen task scope",
}

DATA_RESULT = {"evidence": [{"rows": [{"month": "2025-08", "revenue": 1234567.89}]}]}

NUMBER_TAMPERS = {
    "digit_changed": "华东区本月收入为1234568.89元。",
    "scaled_ten_times": "华东区本月收入为12345678.9元。",
    "invented_percentage": "华东区本月收入下降了12.5%。",
    "wrong_rounding": "华东区本月收入约为1234500元。",
}
NUMBER_CONTROLS = {
    "exact_value": "华东区本月收入为1234567.89元。",
    "same_precision_rounding": "华东区本月收入约为1234567.9元。",
    "no_numbers": "华东区收入出现下降。",
}


@dataclass(frozen=True)
class GateOutcome:
    name: str
    gate: str
    expected_blocked: bool
    blocked: bool

    @property
    def correct(self) -> bool:
        return self.expected_blocked == self.blocked


def _report_blocked(report: dict, expected_reason: str | None = None) -> bool:
    try:
        validate_report(report, allowed_chunk_ids=ALLOWED_CHUNK_IDS)
    except ReportValidationError as exc:
        return expected_reason is None or expected_reason in str(exc)
    return False


def run_report_gate_evaluation() -> dict:
    outcomes = [
        GateOutcome("valid_report", "report", False, _report_blocked(base_report()))
    ]
    outcomes += [
        GateOutcome(
            name, "report", True, _report_blocked(build(), EXPECTED_REASONS[name])
        )
        for name, build in REPORT_TAMPERS.items()
    ]
    outcomes += [
        GateOutcome(
            name,
            "numbers",
            True,
            not validate_numbers(text, copy.deepcopy(DATA_RESULT))[0],
        )
        for name, text in NUMBER_TAMPERS.items()
    ]
    outcomes += [
        GateOutcome(
            name,
            "numbers",
            False,
            not validate_numbers(text, copy.deepcopy(DATA_RESULT))[0],
        )
        for name, text in NUMBER_CONTROLS.items()
    ]
    tampered = [o for o in outcomes if o.expected_blocked]
    controls = [o for o in outcomes if not o.expected_blocked]
    return {
        "tampered_cases": len(tampered),
        "interception_rate": sum(o.blocked for o in tampered) / len(tampered),
        "control_cases": len(controls),
        "false_block_rate": sum(o.blocked for o in controls) / len(controls),
        "failures": [o.name for o in outcomes if not o.correct],
        "outcomes": [o.__dict__ for o in outcomes],
    }
