import pytest
from app.modules.analysis.tool_protocol import Tool, ToolInput, ToolOutput
from app.modules.runtime.tool_runtime import RuntimeTool, ToolGateway, ToolRuntime
from app.modules.runtime.tools import pipeline
from app.modules.runtime.tools.pipeline import STAGE_ORDER, PipelineOrderError


class _Named(Tool):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "fake"

    def execute(self, input: ToolInput) -> ToolOutput:
        raise AssertionError("tools run only through the runtime")


def _recording_stages(stop_at: str | None = None):
    ran: list[str] = []

    def make(name):
        def stage(call):
            ran.append(name)
            if name == stop_at or name == "execute":
                return ToolOutput(success=name == "execute", error_code=name)
            return None

        return stage

    return [(name, make(name)) for name in STAGE_ORDER], ran


def test_checks_come_before_budget_and_budget_before_execution():
    # Locking the order: moving any check after "execute" must fail this test.
    assert STAGE_ORDER == (
        "allowlist",
        "current_authorization",
        "input_schema",
        "scope",
        "document_visibility",
        "server_parameters",
        "budget",
        "execute",
    )


def test_runtime_builds_its_stages_in_the_contract_order():
    runtime = object.__new__(ToolRuntime)  # building the list needs no database

    assert tuple(name for name, _ in runtime._stages()) == STAGE_ORDER


@pytest.mark.parametrize("stop_at", STAGE_ORDER[:-1])
def test_a_stage_that_answers_stops_every_later_stage(stop_at):
    stages, ran = _recording_stages(stop_at)

    output = pipeline.run(stages, call=object())

    assert output.error_code == stop_at
    assert ran == list(STAGE_ORDER[: STAGE_ORDER.index(stop_at) + 1])
    assert "execute" not in ran


def test_a_call_that_passes_every_check_executes_once():
    stages, ran = _recording_stages()

    assert pipeline.run(stages, call=object()).success
    assert ran == list(STAGE_ORDER)


@pytest.mark.parametrize(
    "reorder",
    [
        lambda stages: [stages[-1], *stages[:-1]],  # execute first
        lambda stages: stages[:2] + stages[3:],  # input_schema skipped
        lambda stages: [stages[1], stages[0], *stages[2:]],  # two checks swapped
    ],
)
def test_a_stage_list_out_of_order_refuses_to_run_anything(reorder):
    stages, ran = _recording_stages()

    with pytest.raises(PipelineOrderError):
        pipeline.run(reorder(stages), call=object())
    assert ran == []


def test_a_pipeline_without_an_answer_is_a_programming_error():
    stages = [(name, lambda call: None) for name in STAGE_ORDER]

    with pytest.raises(PipelineOrderError):
        pipeline.run(stages, call=object())


class _FakeRuntime:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []

    def resolve_empty_document_scope(self, tool, input):
        return None

    def execute(self, tool, input):
        self.executed.append((tool.name, input.parameters))
        return ToolOutput(success=True, data="ran")


def test_gateway_calls_a_registered_tool_by_name_through_the_runtime():
    runtime = _FakeRuntime()
    gateway = ToolGateway(runtime)  # type: ignore[arg-type]
    gateway.register(_Named("sql_query"))

    assert gateway.call("sql_query", {"sql": "select 1"}).data == "ran"
    assert runtime.executed == [("sql_query", {"sql": "select 1"})]


def test_gateway_refuses_a_name_nobody_registered():
    runtime = _FakeRuntime()
    gateway = ToolGateway(runtime)  # type: ignore[arg-type]

    output = gateway.call("drop_everything", {})

    assert output.error_code == "tool_unknown"
    assert runtime.executed == []


def test_wrapped_tools_enter_only_through_the_gateway():
    runtime = _FakeRuntime()
    gateway = ToolGateway(runtime)  # type: ignore[arg-type]
    tool = _Named("rag_search")
    gateway.register(tool)

    RuntimeTool(gateway, tool).execute(ToolInput(parameters={"question": "q"}))

    assert runtime.executed == [("rag_search", {"question": "q"})]
