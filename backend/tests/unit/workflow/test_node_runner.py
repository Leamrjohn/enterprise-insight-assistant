import pytest
from app.modules.runtime.model_governance import ModelCallCancelled
from app.modules.workflow.orchestration import nodes
from app.modules.workflow.orchestration.node_runner import NodeStep, run_node


def _state(events: list, *, cancelled: bool = False, **extra) -> dict:
    return {
        "question": "q",
        "cancel_check": lambda: events.append("cancel_check") or cancelled,
        "stage_callback": lambda stage, node: events.append(("stage", stage, node)),
        "checkpoint_callback": lambda done, nxt, snap: events.append(
            ("checkpoint", done, nxt, snap)
        ),
        **extra,
    }


def test_order_is_cancel_stage_node_checkpoint():
    events: list = []

    def body(state):
        events.append("body")
        return NodeStep(next_node="reviewer_node", update={"data_result": {"rows": 1}})

    node = run_node("data_node", "querying_data", body)
    result = node(_state(events))

    assert result == {"data_result": {"rows": 1}}
    assert events == [
        "cancel_check",
        ("stage", "querying_data", "data_node"),
        "body",
        ("checkpoint", "data_node", "reviewer_node", {"data_result": {"rows": 1}}),
    ]


def test_cancelled_task_stops_before_stage_and_node():
    events: list = []
    node = run_node("data_node", "querying_data", lambda s: events.append("body"))

    with pytest.raises(ModelCallCancelled):
        node(_state(events, cancelled=True))

    assert events == ["cancel_check"]


def test_skipped_node_writes_no_stage_or_checkpoint():
    events: list = []
    node = run_node(
        "state_extract_node",
        "planning",
        lambda s: events.append("body"),
        skip_if=lambda s: True,
    )

    assert node(_state(events)) == {}
    assert events == ["cancel_check"]


def test_plain_dict_result_is_not_checkpointed_and_stage_none_is_silent():
    events: list = []
    node = run_node("planner_terminal_node", None, lambda s: {"final_answer": "a"})

    assert node(_state(events)) == {"final_answer": "a"}
    assert events == ["cancel_check"]


def test_missing_callbacks_are_optional():
    node = run_node(
        "data_node", "querying_data", lambda s: NodeStep(next_node=None, update={})
    )

    assert node({"question": "q"}) == {}


@pytest.mark.parametrize(
    "name",
    [
        "state_extract_node",
        "planner_node",
        "planner_semantic_review_node",
        "planner_terminal_node",
        "planning_failure_node",
        "data_node",
        "knowledge_node",
        "reviewer_node",
        "smart_router_node",
    ],
)
def test_every_graph_node_goes_through_run_node(name):
    node = getattr(nodes, name)

    assert node.__name__ == name
    assert node.__wrapped__.__name__ == f"_{name}"
    with pytest.raises(ModelCallCancelled):
        node(_state([], cancelled=True))
