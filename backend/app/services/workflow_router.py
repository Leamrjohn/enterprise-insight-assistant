"""Deterministic, bounded routing policy for one analysis workflow invocation."""

from __future__ import annotations

import hashlib
import json
from typing import Literal


RoutingAction = Literal["stop", "retry_data", "retry_knowledge", "replan"]

MAX_EXTERNAL_RETRIES = 2
RETRYABLE_DATA_CODES = frozenset(
    {
        "business_db_execution_failed",
        "sql_generation_retryable_error",
        "sql_generation_invalid_output",
        "data_attempt_budget_exhausted",
    }
)
RETRYABLE_KNOWLEDGE_CODES = frozenset({"knowledge_retrieval_failed"})
SECURITY_VALIDATION_FAILURES = frozenset({"citations_valid"})


def build_scope_fingerprint(state: dict, plan: dict | None = None) -> str:
    """Bind reusable artifacts to the user, company, question, plan and documents."""
    source = state.get("business_data_source")
    payload = {
        "user_id": state.get("user_id"),
        "company_id": state.get("company_id"),
        "document_ids": sorted(state.get("document_ids") or []),
        "question": (plan or state.get("plan") or {}).get("resolved_question")
        or state.get("question"),
        "route": (plan or state.get("plan") or {}).get("route"),
        "data_source_id": getattr(source, "id", None),
        "schema_snapshot": state.get("schema_catalog"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validation_action(review_result: dict) -> RoutingAction | None:
    validation = review_result.get("answer_validation")
    if not isinstance(validation, dict):
        return None
    invalid_fields = {
        name
        for name in ("schema_valid", "numbers_valid", "citations_valid")
        if validation.get(name) is False
    }
    if not invalid_fields:
        return None
    if invalid_fields & SECURITY_VALIDATION_FAILURES:
        return "stop"
    return "replan"


def choose_next_action(state: dict) -> tuple[RoutingAction, str]:
    """Return a policy decision without asking an LLM or inspecting answer prose."""
    review_result = state.get("review_result") or {}
    validation_action = _validation_action(review_result)
    if validation_action is not None:
        return validation_action, "validation_failure"

    data_result = state.get("data_result") or {}
    knowledge_result = state.get("knowledge_result") or {}
    data_status = data_result.get("status")
    knowledge_status = knowledge_result.get("status")
    data_code = data_result.get("error_code")
    knowledge_code = knowledge_result.get("error_code")

    # Empty data can be a planner scope/alias mismatch once, rather than a fact.
    if data_code == "no_matching_records" and not state.get("empty_result_replanned"):
        return "replan", "empty_result_scope_check"

    if data_status == "ready" and knowledge_status in {
        "ready",
        "insufficient_evidence",
        None,
    }:
        if (
            knowledge_status == "ready"
            or (state.get("plan") or {}).get("route") == "data_only"
        ):
            return "stop", "evidence_complete"
        return "stop", "knowledge_insufficient"
    if knowledge_status == "ready" and data_status == "insufficient_evidence":
        return "stop", "data_insufficient"
    if (
        data_status == "insufficient_evidence"
        and knowledge_status == "insufficient_evidence"
    ):
        return "stop", "evidence_exhausted"

    if data_status == "failed" and data_code in RETRYABLE_DATA_CODES:
        if knowledge_status == "ready":
            return "retry_data", "retryable_data_failure"
        if knowledge_status == "insufficient_evidence":
            return "stop", "knowledge_insufficient"
        if knowledge_status == "failed" and knowledge_code in RETRYABLE_KNOWLEDGE_CODES:
            return "replan", "both_sources_retryable"
    if knowledge_status == "failed" and knowledge_code in RETRYABLE_KNOWLEDGE_CODES:
        if data_status == "ready":
            return "retry_knowledge", "retryable_knowledge_failure"
        if data_status == "insufficient_evidence":
            return "stop", "data_insufficient"

    return "stop", "non_retryable_or_unknown_failure"


def build_feedback(state: dict, action: RoutingAction, reason: str) -> dict | None:
    if action == "stop":
        return None
    data_result = state.get("data_result") or {}
    knowledge_result = state.get("knowledge_result") or {}
    review_result = state.get("review_result") or {}
    validation = review_result.get("answer_validation") or {}
    if action == "retry_data":
        candidate = data_result.get("candidate") or {}
        previous_sql = candidate.get("sql")
        return {
            "target": "data",
            "mode": (
                "replay_validated_sql"
                if isinstance(previous_sql, str)
                else "retry_generation"
            ),
            "error_code": data_result.get("error_code"),
            "previous_sql": previous_sql,
            "purpose": candidate.get("purpose"),
            "query_contract": candidate.get("query_contract"),
            "reason": reason,
            "suggestion": (
                "重放已通过受控 SQL 校验的语句，不改变查询口径。"
                if isinstance(previous_sql, str)
                else "上次 SQL 生成未完成；保留原问题和计划后重新生成受控 SQL。"
            ),
        }
    if action == "retry_knowledge":
        return {
            "target": "knowledge",
            "mode": "retry_same_scope",
            "error_code": knowledge_result.get("error_code"),
            "reason": reason,
            "suggestion": "保持问题、公司和文档范围不变，重试文档检索与引用生成。",
        }
    return {
        "target": "planner",
        "reason": reason,
        "data_available": data_result.get("status") == "ready",
        "knowledge_available": knowledge_result.get("status") == "ready",
        "validation_failures": {
            key: value
            for key, value in validation.items()
            if key.endswith("_valid") and value is False
        },
        "suggestion": (
            "检查上轮的范围别名、指标口径或证据相关性；可改为 data_only、"
            "needs_clarification，或明确证据不足。"
        ),
    }
