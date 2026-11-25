"""T2: every tool error code belongs to exactly one class, and the class decides
what happens next.  This table is the only place a code is classified."""

from enum import StrEnum


class ErrorClass(StrEnum):
    CALLER = "caller_error"  # The request was wrong: hand it back to be fixed.
    DENIED = "denied"  # Permission or scope: stop at once, never retry.
    INFRA = "infra_error"  # A dependency failed: retry, count toward the breaker.
    EXHAUSTED = "exhausted"  # A tool budget ran out: end this loop.
    TASK_STOP = "task_stop"  # Cancelled or model budget spent: let it propagate.


ERROR_CLASSES: dict[str, ErrorClass] = {
    # Runtime authorization and scope (ToolRuntime._deny).
    "tool_not_allowlisted": ErrorClass.DENIED,
    "tool_schema_unregistered": ErrorClass.DENIED,
    "tool_company_scope_missing": ErrorClass.DENIED,
    "tool_company_scope_denied": ErrorClass.DENIED,
    "tool_current_authorization_denied": ErrorClass.DENIED,
    "tool_document_scope_denied": ErrorClass.DENIED,
    "tool_document_current_authorization_denied": ErrorClass.DENIED,
    "tool_task_missing": ErrorClass.DENIED,
    "data_source_not_allowed": ErrorClass.DENIED,
    "mcp_runtime_context_invalid": ErrorClass.DENIED,
    "mcp_runtime_context_mismatch": ErrorClass.DENIED,
    "tool_context_signature_invalid": ErrorClass.DENIED,
    "tool_context_expired": ErrorClass.DENIED,
    # The caller's own request.
    "tool_input_schema_invalid": ErrorClass.CALLER,
    "tool_arguments_not_json": ErrorClass.CALLER,
    "tool_arguments_invalid": ErrorClass.CALLER,
    "tool_unknown": ErrorClass.CALLER,
    "sql_input_missing": ErrorClass.CALLER,
    "sql_validation_error": ErrorClass.CALLER,
    "sql_semantic_error": ErrorClass.CALLER,
    # A timeout is usually the statement's fault, so the model is asked to fix it.
    "sql_statement_timeout": ErrorClass.CALLER,
    "rag_input_missing": ErrorClass.CALLER,
    "rag_validity_window_invalid": ErrorClass.CALLER,
    "template_query_invalid_request": ErrorClass.CALLER,
    # Dependencies, and configuration or code no rewording can fix.
    "business_db_execution_failed": ErrorClass.INFRA,
    "rag_search_unavailable": ErrorClass.INFRA,
    "rag_retrieval_failed": ErrorClass.INFRA,
    "local_embedding_failed": ErrorClass.INFRA,
    "local_rerank_failed": ErrorClass.INFRA,
    "template_query_execution_failed": ErrorClass.INFRA,
    "template_query_not_implemented": ErrorClass.INFRA,
    "sql_timeout_policy_invalid": ErrorClass.INFRA,
    "rag_timeout_policy_invalid": ErrorClass.INFRA,
    "mcp_transport_unavailable": ErrorClass.INFRA,
    "mcp_evidence_read_failed": ErrorClass.INFRA,
    "mcp_evidence_read_malformed": ErrorClass.INFRA,
    "mcp_response_malformed": ErrorClass.INFRA,
    "mcp_sdk_version_mismatch": ErrorClass.INFRA,
    "mcp_catalog_mismatch": ErrorClass.INFRA,
    "mcp_input_required_not_supported": ErrorClass.INFRA,
    "tool_circuit_open": ErrorClass.INFRA,
    "tool_runtime_unexpected_error": ErrorClass.INFRA,
    # Budgets.
    "tool_budget_exhausted": ErrorClass.EXHAUSTED,
    "model_budget_exhausted": ErrorClass.TASK_STOP,
    "task_cancelled": ErrorClass.TASK_STOP,
}


def classify(code: str | None) -> ErrorClass:
    """The class of a failed tool call's error code.

    A missing or unregistered code is treated as INFRA: a failure nobody named
    must not be handed back to the model as if it could fix it.
    """
    return ERROR_CLASSES.get(code or "", ErrorClass.INFRA)
