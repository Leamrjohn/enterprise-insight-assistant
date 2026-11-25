import ast
from pathlib import Path

import pytest
from app.modules.analysis.tool_protocol import ToolInput, ToolOutput
from app.modules.knowledge.tool import RAGTool
from app.modules.runtime.tool_guard import is_infrastructure_failure, outcome_of_failure
from app.modules.runtime.tools.errors import ERROR_CLASSES, ErrorClass, classify

APP = Path(__file__).resolve().parents[3] / "app" / "modules"
# Every file that builds a tool's failure.
TOOL_LAYER = [
    APP / "runtime" / "tool_runtime.py",
    APP / "runtime" / "tool_guard.py",
    APP / "runtime" / "tool_loop.py",
    APP / "runtime" / "model_governance.py",
    APP.parent / "tool_service" / "server.py",
    APP / "runtime" / "tools" / "mcp_client.py",
    APP / "knowledge" / "tool.py",
    APP / "knowledge" / "mcp_adapter.py",
    APP / "analysis" / "data" / "sql_tool.py",
    APP / "analysis" / "data" / "template_query.py",
]


def _calls_named(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            called = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", None)
            )
            if called == name:
                yield node


def _literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _codes_in(tree: ast.AST) -> set[str]:
    codes: set[str] = set()
    for call in [
        *_calls_named(tree, "ToolOutput"),
        *_calls_named(tree, "ServiceReply"),
    ]:
        for keyword in call.keywords:
            if keyword.arg == "error_code" and (code := _literal(keyword.value)):
                codes.add(code)
    for call in _calls_named(tree, "_deny"):
        if len(call.args) > 1 and (code := _literal(call.args[1])):
            codes.add(code)
    for call in _calls_named(tree, "ToolReply"):
        if len(call.args) > 2 and (code := _literal(call.args[2])):
            codes.add(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if _literal(key) == "error_code" and (code := _literal(value)):
                    codes.add(code)
        if isinstance(node, ast.Assign) and (code := _literal(node.value)):
            names = {getattr(target, "id", None) for target in node.targets}
            if names & {"code", "CIRCUIT_OPEN_CODE"}:
                codes.add(code)
    return codes


def test_every_error_code_in_the_tool_layer_is_classified():
    found: set[str] = set()
    for path in TOOL_LAYER:
        found |= _codes_in(ast.parse(path.read_text(encoding="utf-8")))

    assert len(found) > 30  # the scan itself still sees the tool layer
    assert sorted(found - ERROR_CLASSES.keys()) == []


def test_no_tool_failure_is_built_without_an_error_code():
    missing = []
    for path in TOOL_LAYER:
        for call in _calls_named(
            ast.parse(path.read_text(encoding="utf-8")), "ToolOutput"
        ):
            keywords = {keyword.arg: keyword.value for keyword in call.keywords}
            success = keywords.get("success")
            if (
                isinstance(success, ast.Constant)
                and success.value is False
                and "error_code" not in keywords
            ):
                missing.append(f"{path.name}:{call.lineno}")

    assert missing == []


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("tool_company_scope_denied", ErrorClass.DENIED),
        ("sql_validation_error", ErrorClass.CALLER),
        ("sql_statement_timeout", ErrorClass.CALLER),
        ("mcp_transport_unavailable", ErrorClass.INFRA),
        ("tool_budget_exhausted", ErrorClass.EXHAUSTED),
        ("task_cancelled", ErrorClass.TASK_STOP),
    ],
)
def test_classify_reads_the_table(code, expected):
    assert classify(code) is expected


@pytest.mark.parametrize("code", [None, "", "never_registered_code"])
def test_unnamed_failures_are_infrastructure(code):
    assert classify(code) is ErrorClass.INFRA


def test_rag_missing_parameters_is_a_caller_error():
    result = RAGTool().execute(ToolInput(parameters={"question": "", "company_id": 1}))

    assert result.error_code == "rag_input_missing"
    assert classify(result.error_code) is ErrorClass.CALLER


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (ToolOutput(success=False, error_code="tool_company_scope_denied"), "denied"),
        # Not in the old hand-written denial set; a scope refusal all the same.
        (ToolOutput(success=False, error_code="data_source_not_allowed"), "denied"),
        (ToolOutput(success=False, error_code="tool_budget_exhausted"), "exhausted"),
        (
            ToolOutput(success=False, error_code="business_db_execution_failed"),
            "unavailable",
        ),
        (ToolOutput(success=False, error_code="rag_search_unavailable"), "unavailable"),
        # An outage stays an outage even when the transport calls itself repairable.
        (
            ToolOutput(
                success=False, error_code="mcp_transport_unavailable", repairable=True
            ),
            "unavailable",
        ),
        (
            ToolOutput(
                success=False,
                error_code="sql_validation_error",
                model_feedback="列名不存在",
            ),
            "repairable",
        ),
        (
            ToolOutput(
                success=False, error_code="sql_statement_timeout", repairable=True
            ),
            "repairable",
        ),
    ],
)
def test_loop_outcome_follows_the_class(output, expected):
    assert outcome_of_failure(output) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("business_db_execution_failed", True),
        ("rag_retrieval_failed", True),
        (None, True),
        ("sql_statement_timeout", False),
        ("tool_company_scope_denied", False),
    ],
)
def test_only_infrastructure_failures_count_toward_the_breaker(code, expected):
    assert (
        is_infrastructure_failure(ToolOutput(success=False, error_code=code))
        is expected
    )
