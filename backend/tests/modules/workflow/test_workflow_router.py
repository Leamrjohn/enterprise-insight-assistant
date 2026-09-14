from app.modules.workflow.router import build_feedback, choose_next_action
from app.modules.workflow.nodes import smart_router_node


def test_retries_only_data_when_knowledge_is_cached() -> None:
    state = {
        "data_result": {
            "status": "failed",
            "error_code": "business_db_execution_failed",
            "candidate": {"sql": "SELECT 1", "purpose": "查询销售额"},
        },
        "knowledge_result": {"status": "ready", "evidences": [{"chunk_id": 7}]},
        "review_result": {},
    }

    action, reason = choose_next_action(state)

    assert (action, reason) == ("retry_data", "retryable_data_failure")
    assert build_feedback(state, action, reason)["previous_sql"] == "SELECT 1"
    assert build_feedback(state, action, reason)["suggestion"]


def test_retries_only_knowledge_when_data_is_ready() -> None:
    action, reason = choose_next_action(
        {
            "data_result": {"status": "ready"},
            "knowledge_result": {
                "status": "failed",
                "error_code": "knowledge_retrieval_failed",
            },
            "review_result": {},
        }
    )

    assert (action, reason) == ("retry_knowledge", "retryable_knowledge_failure")


def test_retries_transient_sql_generation_failure_without_replaying_missing_sql() -> (
    None
):
    state = {
        "data_result": {
            "status": "failed",
            "error_code": "sql_generation_retryable_error",
        },
        "knowledge_result": {"status": "ready"},
        "review_result": {},
    }

    action, reason = choose_next_action(state)

    assert (action, reason) == ("retry_data", "retryable_data_failure")
    assert build_feedback(state, action, reason)["mode"] == "retry_generation"


def test_stops_when_both_sources_are_objectively_insufficient() -> None:
    action, reason = choose_next_action(
        {
            "data_result": {"status": "insufficient_evidence"},
            "knowledge_result": {"status": "insufficient_evidence"},
            "review_result": {},
        }
    )

    assert (action, reason) == ("stop", "evidence_exhausted")


def test_replans_once_after_empty_result_to_check_scope_alias() -> None:
    state = {
        "data_result": {
            "status": "insufficient_evidence",
            "error_code": "no_matching_records",
        },
        "knowledge_result": {"status": "insufficient_evidence"},
        "review_result": {},
        "empty_result_replanned": False,
    }

    assert choose_next_action(state) == ("replan", "empty_result_scope_check")
    state["empty_result_replanned"] = True
    assert choose_next_action(state) == ("stop", "evidence_exhausted")


def test_node_outcome_keeps_empty_business_data_distinct_from_failure() -> None:
    action, reason = choose_next_action(
        {
            "data_outcome": {
                "status": "no_matching_records",
                "output": {},
                "error_code": "no_matching_records",
                "retry_hint": "stop",
                "checkpoint_patch": {},
            },
            "knowledge_result": {"status": "insufficient_evidence"},
            "review_result": {},
        }
    )

    assert (action, reason) == ("stop", "no_matching_records")


def test_node_outcome_denied_never_retries_or_exposes_repair_context() -> None:
    state = {
        "data_outcome": {
            "status": "denied",
            "output": {},
            "error_code": "sql_forbidden_table",
            "retry_hint": "stop",
            "checkpoint_patch": {},
        },
        "knowledge_result": {"status": "ready"},
        "review_result": {},
    }

    action, reason = choose_next_action(state)

    assert (action, reason) == ("stop", "data_denied")
    assert build_feedback(state, action, reason) is None


def test_reviewer_retryable_outcome_retries_same_evidence() -> None:
    state = {
        "data_result": {"status": "ready"},
        "knowledge_result": {"status": "ready"},
        "review_result": {},
        "reviewer_outcome": {
            "status": "retryable_error",
            "output": {},
            "error_code": "reviewer_rate_limited",
            "retry_hint": "retry",
            "checkpoint_patch": {},
        },
    }

    action, reason = choose_next_action(state)

    assert (action, reason) == ("retry_reviewer", "retryable_reviewer_failure")
    assert build_feedback(state, action, reason)["mode"] == "retry_same_evidence"


def test_security_citation_failure_never_replans() -> None:
    action, reason = choose_next_action(
        {
            "data_result": {"status": "ready"},
            "knowledge_result": {"status": "ready"},
            "review_result": {
                "answer_validation": {
                    "schema_valid": True,
                    "numbers_valid": True,
                    "citations_valid": False,
                }
            },
        }
    )

    assert (action, reason) == ("stop", "validation_failure")


def test_numeric_validation_failure_replans() -> None:
    action, reason = choose_next_action(
        {
            "data_result": {"status": "ready"},
            "knowledge_result": {"status": "ready"},
            "review_result": {
                "answer_validation": {
                    "schema_valid": True,
                    "numbers_valid": False,
                    "citations_valid": True,
                }
            },
        }
    )

    assert (action, reason) == ("replan", "validation_failure")


def test_smart_router_stops_at_the_external_retry_budget() -> None:
    result = smart_router_node(
        {
            "external_retry_count": 2,
            "max_external_retries": 2,
            "loop_history": [],
            "data_result": {
                "status": "failed",
                "error_code": "business_db_execution_failed",
            },
            "knowledge_result": {"status": "ready"},
            "review_result": {},
        }
    )

    assert result["routing_action"] == "stop"
    assert result["loop_stop_reason"] == "external_retry_budget_exhausted"


def test_smart_router_preserves_an_existing_terminal_result() -> None:
    result = smart_router_node(
        {
            "external_retry_count": 0,
            "max_external_retries": 2,
            "loop_history": [],
            "data_result": {"status": "ready"},
            "knowledge_result": {"status": "ready"},
            "review_result": {},
            "terminal_result": {"outcome": "needs_clarification", "reason": "保留原因"},
        }
    )

    assert result["terminal_result"] == {
        "outcome": "needs_clarification",
        "reason": "保留原因",
    }
