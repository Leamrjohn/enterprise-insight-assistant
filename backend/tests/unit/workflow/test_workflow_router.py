import pytest
from app.modules.workflow.orchestration.nodes import smart_router_node
from app.modules.workflow.orchestration.router import build_feedback, choose_next_action


@pytest.mark.parametrize("data_result", [None, {"status": "not_run"}])
def test_ready_knowledge_only_finishes_without_sql(data_result) -> None:
    result = smart_router_node(
        {
            "plan": {"route": "knowledge_only"},
            "data_result": data_result,
            "knowledge_result": {"status": "ready"},
            "review_result": {"review_status": "completed"},
            "reviewer_outcome": {"status": "succeeded"},
        }
    )

    assert result["terminal_result"] == {
        "outcome": "completed",
        "reason": "evidence_complete",
    }


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"plan": {"route": "hybrid"}}, ("stop", "non_retryable_or_unknown_failure")),
        (
            {"plan": {"route": "data_only"}},
            ("stop", "non_retryable_or_unknown_failure"),
        ),
        (
            {"data_result": {"status": "failed"}},
            ("stop", "non_retryable_or_unknown_failure"),
        ),
        ({"knowledge_outcome": {"status": "denied"}}, ("stop", "knowledge_denied")),
        ({"knowledge_outcome": {"status": "cancelled"}}, ("stop", "cancelled")),
        (
            {"reviewer_outcome": {"status": "retryable_error", "retry_hint": "retry"}},
            ("retry_reviewer", "retryable_reviewer_failure"),
        ),
        (
            {"review_result": {"answer_validation": {"citations_valid": False}}},
            ("stop", "validation_failure"),
        ),
        (
            {"review_result": {"answer_validation": {"numbers_valid": False}}},
            ("replan", "validation_failure"),
        ),
    ],
)
def test_ready_knowledge_does_not_bypass_other_requirements(override, expected) -> None:
    state = {
        "plan": {"route": "knowledge_only"},
        "data_result": None,
        "knowledge_result": {"status": "ready"},
        "review_result": {"review_status": "completed"},
        **override,
    }
    assert choose_next_action(state) == expected


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


def test_hybrid_empty_evidence_has_insufficient_terminal_outcome() -> None:
    result = smart_router_node(
        {
            "external_retry_count": 0,
            "max_external_retries": 2,
            "loop_history": [],
            "plan": {"route": "hybrid"},
            "data_result": {"status": "insufficient_evidence"},
            "knowledge_result": {"status": "insufficient_evidence"},
            "review_result": {"review_status": "partial"},
        }
    )

    assert result["terminal_result"] == {
        "outcome": "insufficient_evidence",
        "reason": "evidence_exhausted",
    }


def test_knowledge_only_insufficient_evidence_has_a_distinct_terminal_outcome() -> None:
    state = {
        "plan": {"route": "knowledge_only"},
        "data_result": {"status": "not_run"},
        "knowledge_result": {"status": "insufficient_evidence"},
        "review_result": {"review_status": "partial"},
    }

    assert choose_next_action(state) == ("stop", "knowledge_insufficient")

    result = smart_router_node(
        {
            "external_retry_count": 0,
            "max_external_retries": 2,
            "loop_history": [],
            **state,
        }
    )

    assert result["terminal_result"] == {
        "outcome": "insufficient_evidence",
        "reason": "knowledge_insufficient",
    }


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

    result = smart_router_node(
        {
            "external_retry_count": 0,
            "max_external_retries": 2,
            "loop_history": [],
            "data_outcome": {
                "status": "no_matching_records",
                "output": {},
                "error_code": "no_matching_records",
                "retry_hint": "stop",
                "checkpoint_patch": {},
            },
            "data_result": {"status": "insufficient_evidence"},
            "knowledge_result": {"status": "insufficient_evidence"},
            "review_result": {},
        }
    )

    assert result["terminal_result"] == {
        "outcome": "insufficient_evidence",
        "reason": "no_matching_records",
    }


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


def test_smart_router_marks_a_denied_data_outcome_as_failed() -> None:
    result = smart_router_node(
        {
            "external_retry_count": 0,
            "max_external_retries": 2,
            "loop_history": [],
            "data_outcome": {
                "status": "denied",
                "output": {},
                "error_code": "metric_contract_insufficient",
                "retry_hint": "stop",
                "checkpoint_patch": {},
            },
            "data_result": {
                "status": "failed",
                "error_code": "metric_contract_insufficient",
            },
            "knowledge_result": {},
            "review_result": {},
        }
    )

    assert result["terminal_result"] == {
        "outcome": "failed",
        "reason": "data_denied",
    }


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


def test_smart_router_creates_bounded_retry_context_for_each_agent() -> None:
    cases = (
        (
            {
                "data_outcome": {
                    "status": "retryable_error",
                    "output": {},
                    "retry_hint": "retry",
                    "error_code": "business_db_execution_failed",
                    "checkpoint_patch": {},
                }
            },
            "data_node",
            "business_db_execution_failed",
        ),
        (
            {
                "knowledge_outcome": {
                    "status": "retryable_error",
                    "output": {},
                    "retry_hint": "retry",
                    "error_code": "knowledge_retrieval_failed",
                    "checkpoint_patch": {},
                }
            },
            "knowledge_node",
            "knowledge_retrieval_failed",
        ),
        (
            {
                "reviewer_outcome": {
                    "status": "retryable_error",
                    "output": {},
                    "retry_hint": "retry",
                    "error_code": "reviewer_rate_limited",
                    "checkpoint_patch": {},
                }
            },
            "reviewer_node",
            "reviewer_rate_limited",
        ),
    )
    for outcome, node, code in cases:
        result = smart_router_node(
            {
                "external_retry_count": 0,
                "max_external_retries": 2,
                "loop_history": [],
                "data_result": {"status": "ready"},
                "knowledge_result": {"status": "ready"},
                "review_result": {},
                **outcome,
            }
        )
        assert result["retry_context"]["failed_node"] == node
        assert result["retry_context"]["error_code"] == code
        assert result["retry_context"]["retry_number"] == 1
        assert result["retry_context"]["recovery_mode"] == (
            "retry_node" if node == "reviewer_node" else "rerun_downstream"
        )


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
