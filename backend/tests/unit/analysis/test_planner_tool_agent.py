"""T11e: the planner's model may look things up, then submits the same plan."""

import json

from app.core.gateway.base import ModelGateway, ToolCall, ToolChatResponse
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.planner.planning import PlanningService
from app.modules.analysis.planner.tool_agent import ToolCallingPlannerAgent
from app.modules.analysis.tool_protocol import Tool, ToolOutput, Toolset
from app.modules.runtime.tool_loop import LoopLimits

PLAN = {
    "action": "analyze",
    "route": "data_only",
    "reason": "需要查询销售额",
    "clarification_question": None,
    "response_message": None,
    "resolved_question": "2025年8月华东区已交付订单的销售额是多少",
}


class _Scripted(ModelGateway):
    def __init__(self, tool_responses=(), chat_outputs=()):
        self.tool_responses = list(tool_responses)
        self.chat_outputs = list(chat_outputs)
        self.offered = []
        self.requests = []

    def chat(self, prompt, system_prompt=None, *, json_mode=False):
        return self.chat_outputs.pop(0)

    def chat_with_tools(self, messages, tools, *, tool_choice="auto"):
        self.requests.append(list(messages))
        self.offered.append([tool["function"]["name"] for tool in tools])
        return self.tool_responses.pop(0)

    def count_tokens(self, text):
        return len(text)


class _Lookup(Tool):
    def __init__(self, name, data):
        self._name, self._data, self.seen = name, data, []

    @property
    def name(self):
        return self._name

    @property
    def description(self):
        return self._name

    def execute(self, input):
        self.seen.append(input.parameters)
        return ToolOutput(success=True, data=self._data)


def _call(name, arguments, call_id="c1"):
    return ToolChatResponse(
        None, (ToolCall(call_id, name, json.dumps(arguments, ensure_ascii=False)),)
    )


def _agent(gateway, *tools):
    return ToolCallingPlannerAgent(
        tools=Toolset.of(*tools),
        planning_service=PlanningService(gateway=gateway, sleeper=lambda _s: None),
        limits=LoopLimits(backoff_seconds=0),
    )


def _run(agent, **context):
    question = "2025年8月华东区销售额是多少"
    return agent.run(AgentInput(question=question, user_id=1, context=context))


def test_a_plan_that_needs_no_lookup_takes_one_model_call():
    gateway = _Scripted([_call("submit_plan", PLAN)])
    memory = _Lookup("memory_search", {"memories": []})

    output = _run(_agent(gateway, memory))

    assert output.success
    assert output.plan["route"] == "data_only"
    assert gateway.offered == [["submit_plan", "memory_search"]]
    assert output.attempts["tool_loop"]["rounds"] == 1
    assert memory.seen == []


def test_the_model_may_look_up_past_conclusions_before_it_plans():
    gateway = _Scripted(
        [
            _call("memory_search", {"query": "华东 销售额"}),
            _call("submit_plan", PLAN, "c2"),
        ]
    )
    memory = _Lookup("memory_search", {"memories": [{"memory_id": 7}]})

    output = _run(_agent(gateway, memory))

    assert output.success
    assert memory.seen == [{"query": "华东 销售额"}]
    replies = [m for m in gateway.requests[1] if m["role"] == "tool"]
    assert json.loads(replies[0]["content"]) == {
        "result": {"memories": [{"memory_id": 7}]}
    }


def test_a_plan_that_breaks_the_contract_goes_back_to_the_model():
    broken = {**PLAN, "route": None}  # analyze requires a route
    gateway = _Scripted(
        [_call("submit_plan", broken), _call("submit_plan", PLAN, "c2")]
    )

    output = _run(_agent(gateway))

    assert output.success
    assert [step["outcome"] for step in output.attempts["tool_loop"]["trace"]] == [
        "repairable",
        "finish",
    ]


def test_a_loop_that_ends_without_a_plan_falls_back_to_the_fixed_route():
    gateway = _Scripted(
        [ToolChatResponse("我觉得应该查数据", ())], chat_outputs=[json.dumps(PLAN)]
    )

    output = _run(_agent(gateway))

    assert output.success
    assert output.plan["route"] == "data_only"
    assert output.attempts["switched_to_fixed"] == "answered_in_text"


def test_feedback_is_planned_on_the_fixed_route():
    gateway = _Scripted(chat_outputs=[json.dumps(PLAN)])

    output = _run(_agent(gateway), feedback={"reason": "需要补充文档证据"})

    assert output.success
    assert gateway.offered == []  # no tool round at all


def test_a_plan_written_as_text_passes_the_same_checks_in_one_call():
    gateway = _Scripted([ToolChatResponse(json.dumps(PLAN, ensure_ascii=False), ())])

    output = _run(_agent(gateway))

    assert output.success
    assert output.plan["route"] == "data_only"
    assert "switched_to_fixed" not in output.attempts
    assert gateway.chat_outputs == []  # the fixed route never ran
