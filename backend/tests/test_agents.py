"""测试四个核心 Agent"""

import json
from decimal import Decimal

from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.agents.protocol import AgentInput
from app.agents.knowledge import KnowledgeAgent
from app.agents.data import DataAgent
from app.agents.planner import PlannerAgent
from app.agents.reviewer import ReviewerAgent
from app.schemas.sql_candidate import SQLCandidate
from app.schemas.plannerdecision import PlannerDecision
from app.schemas.semantic_review import EvidenceSemanticReview, SQLSemanticReview
from app.tools.protocol import ToolInput, ToolOutput


class FakeSQLGenerator:
    def __init__(
        self,
        candidate: SQLCandidate | None = None,
        error: Exception | None = None,
        outcomes: list[SQLCandidate | Exception] | None = None,
    ) -> None:
        self.outcomes = outcomes or [error if error is not None else candidate]
        self.questions: list[str] = []
        self.calls: list[dict[str, str | None]] = []

    def generate(
        self,
        question: str,
        *,
        repair_reason: str | None = None,
        previous_sql: str | None = None,
    ) -> SQLCandidate:
        self.questions.append(question)
        self.calls.append(
            {
                "question": question,
                "repair_reason": repair_reason,
                "previous_sql": previous_sql,
            }
        )
        outcome = self.outcomes[len(self.calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        assert outcome is not None
        return outcome


class FakeSQLTool:
    def __init__(self, output: ToolOutput | list[ToolOutput]) -> None:
        self.outputs = output if isinstance(output, list) else [output]
        self.inputs: list[ToolInput] = []

    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        return self.outputs[len(self.inputs) - 1]


class FakeSemanticReviewer:
    def __init__(self, sql_review=None, evidence_review=None) -> None:
        self.sql_review = sql_review
        self.evidence_review = evidence_review
        self.sql_calls: list[dict] = []
        self.evidence_calls: list[dict] = []

    def review_sql(self, **kwargs):
        self.sql_calls.append(kwargs)
        assert self.sql_review is not None
        return self.sql_review

    def review_evidence(self, **kwargs):
        self.evidence_calls.append(kwargs)
        assert self.evidence_review is not None
        return self.evidence_review


class FakeRAGTool:
    def __init__(self, output: ToolOutput) -> None:
        self.output = output
        self.inputs: list[ToolInput] = []

    def execute(self, input: ToolInput) -> ToolOutput:
        self.inputs.append(input)
        return self.output


class FakeModelGateway:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict] = []

    def chat(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        json_mode: bool = False,
    ) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "json_mode": json_mode,
            }
        )
        return self.response


class FakePlanningService:
    def __init__(
        self,
        decision: PlannerDecision | None = None,
        error: Exception | None = None,
    ) -> None:
        self.decision = decision
        self.error = error
        self.questions: list[str] = []
        self.conversation_contexts: list[dict | None] = []
        self.model_attempts = 1

    def decide(
        self,
        question: str,
        *,
        conversation_context: dict | None = None,
        repair_reason: str | None = None,
    ) -> PlannerDecision:
        self.questions.append(question)
        self.conversation_contexts.append(conversation_context)
        if self.error is not None:
            raise self.error
        assert self.decision is not None
        return self.decision


def test_knowledge_agent_interface():
    agent = KnowledgeAgent()
    assert agent.name == "knowledge"
    assert len(agent.description) > 0
    assert len(agent.allowed_tools) == 1


def test_knowledge_agent_exists():
    agent = KnowledgeAgent()
    assert agent is not None
    assert isinstance(agent.name, str)
    assert isinstance(agent.description, str)


def test_knowledge_agent_keeps_metadata_for_cited_chunks_only():
    rag_tool = FakeRAGTool(
        ToolOutput(
            success=True,
            data={
                "status": "ready",
                "evidences": [
                    {
                        "chunk_id": 11,
                        "document_id": 3,
                        "content": "无关片段",
                        "score": 0.71,
                    },
                    {
                        "chunk_id": 42,
                        "document_id": 5,
                        "content": "客户合同到期后尚未续约。",
                        "score": 0.93,
                        "rerank_score": 0.98,
                    },
                ],
                "system_prompt": "system prompt",
                "user_prompt": "user prompt",
                "allowed_chunk_ids": [11, 42],
            },
        )
    )
    gateway = FakeModelGateway(
        '{"answer": "合同到期可能影响销售。", "citations": [{"chunk_id": 42}]}'
    )
    agent = KnowledgeAgent(rag_tool=rag_tool, gateway=gateway)

    result = agent.run(AgentInput(question="销售为什么下降？", user_id=7))

    assert result.success is True
    assert rag_tool.inputs[0].parameters == {
        "question": "销售为什么下降？",
    }
    assert gateway.calls[0]["json_mode"] is True
    assert result.evidence == [
        {
            "chunk_id": 42,
            "document_id": 5,
            "content": "客户合同到期后尚未续约。",
            "score": 0.93,
            "rerank_score": 0.98,
        }
    ]


def test_knowledge_agent_does_not_call_model_when_evidence_is_insufficient():
    rag_tool = FakeRAGTool(
        ToolOutput(
            success=True,
            data={
                "status": "insufficient_evidence",
                "answer": "无法回答：资料不足",
                "evidences": [],
            },
        )
    )
    gateway = FakeModelGateway("this response must not be used")
    agent = KnowledgeAgent(rag_tool=rag_tool, gateway=gateway)

    result = agent.run(AgentInput(question="销售为什么下降？", user_id=7))

    assert result.success is True
    assert result.answer == "无法回答：资料不足"
    assert result.evidence == []
    assert gateway.calls == []


def test_knowledge_agent_downgrades_invalid_model_output_to_insufficient_evidence():
    rag_tool = FakeRAGTool(
        ToolOutput(
            success=True,
            data={
                "status": "ready",
                "evidences": [
                    {
                        "chunk_id": 42,
                        "document_id": 5,
                        "content": "客户合同到期后尚未续约。",
                        "score": 0.93,
                    }
                ],
                "system_prompt": "system prompt",
                "user_prompt": "user prompt",
                "allowed_chunk_ids": [42],
            },
        )
    )
    gateway = FakeModelGateway('{"answer": "没有引用"}')
    agent = KnowledgeAgent(rag_tool=rag_tool, gateway=gateway)

    result = agent.run(AgentInput(question="销售为什么下降？", user_id=7))

    assert result.success is True
    assert result.evidence == []
    assert result.error_code == "knowledge_invalid_output"
    assert "可引用" in (result.answer or "")


def test_knowledge_agent_retries_the_same_question_and_scope_without_feedback_injection():
    rag_tool = FakeRAGTool(
        ToolOutput(
            success=True,
            data={
                "status": "insufficient_evidence",
                "answer": "无法回答：资料不足",
                "evidences": [],
            },
        )
    )
    agent = KnowledgeAgent(rag_tool=rag_tool)

    result = agent.run(
        AgentInput(
            question="销售为什么下降？",
            user_id=7,
            context={
                "company_id": 3,
                "document_ids": [5],
                "feedback": {
                    "target": "knowledge",
                    "mode": "retry_same_scope",
                },
            },
        )
    )

    assert rag_tool.inputs[0].parameters == {
        "question": "销售为什么下降？",
        "company_id": 3,
        "document_ids": [5],
    }
    assert result.attempts == {"same_scope_retry": 1}


def test_data_agent_interface():
    agent = DataAgent()
    assert agent.name == "data"
    assert len(agent.description) > 0
    assert len(agent.allowed_tools) == 1


def test_data_agent_generates_and_executes_candidate_sql():
    generator = FakeSQLGenerator(
        candidate=SQLCandidate(
            sql="SELECT o.total_amount FROM sales_orders AS o",
            purpose="查询销售额",
        )
    )
    tool = FakeSQLTool(
        ToolOutput(
            success=True,
            data={"columns": ["total_amount"], "rows": [(100.0,)]},
        )
    )
    agent = DataAgent(sql_generator=generator, sql_tool=tool)

    result = agent.run(AgentInput(question="销售额是多少？", user_id=1))

    assert result.success is True
    assert generator.questions == ["销售额是多少？"]
    assert tool.inputs[0].parameters == {
        "sql": "SELECT o.total_amount FROM sales_orders AS o"
    }
    assert result.evidence[0]["sql"] == "SELECT o.total_amount FROM sales_orders AS o"
    assert result.evidence[0]["columns"] == ["total_amount"]
    assert result.evidence[0]["rows"] == [[100.0]]
    assert result.evidence[0]["result_assessment"]["status"] == "supported"


def test_data_agent_evidence_is_json_serializable():
    generator = FakeSQLGenerator(
        candidate=SQLCandidate(
            sql="SELECT o.total_amount FROM sales_orders AS o",
            purpose="查询销售额",
        )
    )
    tool = FakeSQLTool(
        ToolOutput(
            success=True,
            data={"columns": ["total_amount"], "rows": [(Decimal("1847604.72"),)]},
        )
    )
    agent = DataAgent(sql_generator=generator, sql_tool=tool)

    result = agent.run(AgentInput(question="销售额是多少？", user_id=1))

    assert result.success is True
    assert result.evidence[0]["rows"] == [["1847604.72"]]
    assert result.attempts == {"model_attempts": 1, "sql_attempts": 1}
    json.dumps(result.evidence)


def test_data_agent_does_not_execute_sql_when_semantic_reviewer_reports_missing_schema():
    candidate = SQLCandidate(
        sql='SELECT id AS "客户编号" FROM customers LIMIT 1',
        purpose="无法计算广告点击率",
        query_contract={
            "required_concepts": ["广告点击率"],
            "expected_columns": ["广告点击率"],
            "result_kind": "aggregate",
        },
    )
    semantic_reviewer = FakeSemanticReviewer(
        sql_review=SQLSemanticReview(
            decision="insufficient_schema",
            reason="快照没有广告曝光量和点击量。",
            missing_requirements=["广告曝光量", "广告点击量"],
        )
    )
    tool = FakeSQLTool(ToolOutput(success=True, data={}))
    agent = DataAgent(
        sql_generator=FakeSQLGenerator(candidate=candidate),
        sql_tool=tool,
        semantic_reviewer=semantic_reviewer,
    )

    result = agent.run(
        AgentInput(
            question="本月广告点击率是多少？",
            user_id=1,
            context={"semantic_review_enabled": True, "plan": {"route": "data_only"}},
        )
    )

    assert result.success is False
    assert result.error_code == "insufficient_schema"
    assert tool.inputs == []
    assert result.evidence[0]["missing_requirements"] == ["广告曝光量", "广告点击量"]


def test_data_agent_rejects_query_contract_that_omits_planned_capability() -> None:
    candidate = SQLCandidate(
        sql='SELECT COUNT(*) AS "订单数量" FROM sales_orders',
        purpose="查询订单数量",
        query_contract={
            "required_concepts": ["订单数量"],
            "expected_columns": ["订单数量"],
            "result_kind": "aggregate",
        },
    )
    agent = DataAgent(
        sql_generator=FakeSQLGenerator(candidate=candidate),
        sql_tool=FakeSQLTool(ToolOutput(success=True, data={})),
    )

    result = agent.run(
        AgentInput(
            question="本月广告点击率是多少？",
            user_id=1,
            context={
                "semantic_review_enabled": True,
                "plan": {
                    "intent": {"required_capabilities": ["广告曝光量", "广告点击量"]}
                },
            },
        )
    )

    assert result.success is False
    assert result.error_code == "query_contract_incomplete"
    assert "广告点击" in (result.error or "")


def test_data_agent_accepts_only_measurement_suffix_variants_in_contract() -> None:
    candidate = SQLCandidate(
        sql='SELECT COUNT(*) AS "销售订单总数" FROM sales_orders',
        purpose="查询销售订单总数",
        query_contract={
            "required_concepts": ["销售订单"],
            "expected_columns": ["销售订单总数"],
            "result_kind": "aggregate",
        },
    )
    semantic_reviewer = FakeSemanticReviewer(
        sql_review=SQLSemanticReview(
            decision="execute", reason="满足查询契约。", missing_requirements=[]
        )
    )
    tool = FakeSQLTool(
        ToolOutput(
            success=True,
            data={"columns": ["销售订单总数"], "rows": [(3,)]},
        )
    )
    agent = DataAgent(
        sql_generator=FakeSQLGenerator(candidate=candidate),
        sql_tool=tool,
        semantic_reviewer=semantic_reviewer,
    )

    result = agent.run(
        AgentInput(
            question="当前销售订单总数是多少？",
            user_id=1,
            context={
                "semantic_review_enabled": True,
                "plan": {"intent": {"required_capabilities": ["销售订单计数"]}},
            },
        )
    )

    assert result.success is True
    assert tool.inputs


def test_data_agent_does_not_retry_permanent_generation_failure():
    generator = FakeSQLGenerator(error=PermanentModelError("模型配置错误"))
    tool = FakeSQLTool(ToolOutput(success=True, data={}))
    agent = DataAgent(sql_generator=generator, sql_tool=tool)

    result = agent.run(AgentInput(question="销售额是多少？", user_id=1))

    assert result.success is False
    assert result.error is not None
    assert "无法生成受控 SQL" in result.error
    assert generator.questions == ["销售额是多少？"]
    assert tool.inputs == []


def test_data_agent_marks_empty_sql_result_as_insufficient_evidence() -> None:
    candidate = SQLCandidate(
        sql='SELECT 1 AS "订单数量" WHERE FALSE',
        purpose="查询订单数量",
    )
    agent = DataAgent(
        sql_generator=FakeSQLGenerator(candidate=candidate),
        sql_tool=FakeSQLTool(
            ToolOutput(success=True, data={"columns": ["订单数量"], "rows": []})
        ),
    )

    result = agent.run(AgentInput(question="订单数量是多少？", user_id=1))

    assert result.success is False
    assert result.error_code == "no_matching_records"
    assert result.evidence[0]["result_assessment"]["status"] == "no_matching_records"
    assert result.attempts == {"model_attempts": 1, "sql_attempts": 1}


def test_data_agent_returns_sql_tool_rejection():
    generator = FakeSQLGenerator(
        candidate=SQLCandidate(
            sql="SELECT d.content FROM business_documents AS d",
            purpose="尝试查询受限资料",
        )
    )
    tool = FakeSQLTool(
        ToolOutput(success=False, error="表 'business_documents' 不在业务目录中")
    )
    agent = DataAgent(sql_generator=generator, sql_tool=tool)

    result = agent.run(AgentInput(question="查询资料", user_id=1))

    assert result.success is False
    assert result.error == "表 'business_documents' 不在业务目录中"


def test_data_agent_repairs_structured_output_once_then_executes_sql():
    repaired_candidate = SQLCandidate(
        sql="SELECT o.total_amount FROM sales_orders AS o",
        purpose="查询销售额",
    )
    generator = FakeSQLGenerator(
        outcomes=[
            StructuredOutputError("模型输出不是 JSON"),
            repaired_candidate,
        ]
    )
    tool = FakeSQLTool(
        ToolOutput(
            success=True,
            data={"columns": ["total_amount"], "rows": [(100.0,)]},
        )
    )
    agent = DataAgent(sql_generator=generator, sql_tool=tool)

    result = agent.run(AgentInput(question="销售额是多少？", user_id=1))

    assert result.success is True
    assert len(generator.calls) == 2
    assert generator.calls[0]["repair_reason"] is None
    assert generator.calls[1]["repair_reason"] == "sql_generation_invalid_output"
    assert tool.inputs[0].parameters == {"sql": repaired_candidate.sql}
    assert result.attempts == {"model_attempts": 2, "sql_attempts": 1}


def test_data_agent_repairs_sql_validation_failure_once_then_succeeds():
    invalid_candidate = SQLCandidate(
        sql="SELECT d.content FROM business_documents AS d",
        purpose="错误查询",
    )
    repaired_candidate = SQLCandidate(
        sql="SELECT o.total_amount FROM sales_orders AS o",
        purpose="查询销售额",
    )
    generator = FakeSQLGenerator(outcomes=[invalid_candidate, repaired_candidate])
    tool = FakeSQLTool(
        [
            ToolOutput(
                success=False,
                error="表 'business_documents' 不在业务目录中",
                error_code="sql_validation_error",
                repairable=True,
            ),
            ToolOutput(
                success=True,
                data={"columns": ["total_amount"], "rows": [(100.0,)]},
            ),
        ]
    )
    agent = DataAgent(sql_generator=generator, sql_tool=tool)

    result = agent.run(AgentInput(question="销售额是多少？", user_id=1))

    assert result.success is True
    assert [call.parameters["sql"] for call in tool.inputs] == [
        invalid_candidate.sql,
        repaired_candidate.sql,
    ]
    assert generator.calls[1] == {
        "question": "销售额是多少？",
        "repair_reason": "sql_validation_error",
        "previous_sql": invalid_candidate.sql,
    }
    assert result.attempts == {"model_attempts": 2, "sql_attempts": 2}


def test_data_agent_does_not_retry_non_repairable_database_failure():
    candidate = SQLCandidate(
        sql="SELECT o.total_amount FROM sales_orders AS o",
        purpose="查询销售额",
    )
    generator = FakeSQLGenerator(candidate=candidate)
    tool = FakeSQLTool(
        ToolOutput(
            success=False,
            error="经营数据查询暂时无法完成。",
            error_code="business_db_execution_failed",
            repairable=False,
        )
    )
    agent = DataAgent(sql_generator=generator, sql_tool=tool)

    result = agent.run(AgentInput(question="销售额是多少？", user_id=1))

    assert result.success is False
    assert result.error_code == "business_db_execution_failed"
    assert len(generator.calls) == 1
    assert len(tool.inputs) == 1
    assert result.attempts == {"model_attempts": 1, "sql_attempts": 1}
    assert result.evidence == [
        {
            "sql": candidate.sql,
            "purpose": candidate.purpose,
            "query_contract": None,
        }
    ]


def test_data_agent_stops_after_two_repairable_sql_failures():
    first_candidate = SQLCandidate(
        sql="SELECT o.total_amount FROM sales_orders AS o",
        purpose="第一次查询",
    )
    second_candidate = SQLCandidate(
        sql="SELECT c.region_code FROM customers AS c",
        purpose="第二次查询",
    )
    generator = FakeSQLGenerator(outcomes=[first_candidate, second_candidate])
    tool = FakeSQLTool(
        [
            ToolOutput(
                success=False,
                error="SQL 校验失败",
                error_code="sql_validation_error",
                repairable=True,
            ),
            ToolOutput(
                success=False,
                error="聚合语义错误",
                error_code="sql_semantic_error",
                repairable=True,
            ),
        ]
    )
    agent = DataAgent(sql_generator=generator, sql_tool=tool)

    result = agent.run(AgentInput(question="销售额是多少？", user_id=1))

    assert result.success is False
    assert result.error_code == "sql_semantic_error"
    assert len(generator.calls) == 2
    assert len(tool.inputs) == 2
    assert result.attempts == {"model_attempts": 2, "sql_attempts": 2}


def test_data_agent_replays_previously_validated_sql_without_regenerating() -> None:
    generator = FakeSQLGenerator(
        candidate=SQLCandidate(sql="SELECT should_not_run", purpose="不应调用")
    )
    tool = FakeSQLTool(
        ToolOutput(success=True, data={"columns": ["销售额"], "rows": [(100,)]})
    )
    agent = DataAgent(sql_generator=generator, sql_tool=tool)

    result = agent.run(
        AgentInput(
            question="销售额是多少？",
            user_id=1,
            context={
                "feedback": {
                    "target": "data",
                    "mode": "replay_validated_sql",
                    "previous_sql": "SELECT total_sales FROM monthly_sales",
                    "purpose": "查询销售额",
                }
            },
        )
    )

    assert result.success is True
    assert generator.calls == []
    assert tool.inputs[0].parameters == {"sql": "SELECT total_sales FROM monthly_sales"}
    assert result.attempts["replayed_sql"] == 1


def test_planner_returns_llm_hybrid_decision_for_causal_sales_question():
    service = FakePlanningService(
        decision=PlannerDecision(
            action="analyze",
            route="hybrid",
            reason="需要数据确认现象并检索资料分析原因。",
            clarification_question=None,
            response_message=None,
            resolved_question="分析销售额下降原因。",
        )
    )
    agent = PlannerAgent(planning_service=service)
    result = agent.run(AgentInput(question="销售额为什么下降", user_id=1))

    assert result.success is True
    assert service.questions == ["销售额为什么下降"]
    assert result.plan == {
        "action": "analyze",
        "route": "hybrid",
        "reason": "需要数据确认现象并检索资料分析原因。",
        "clarification_question": None,
        "response_message": None,
        "resolved_question": "分析销售额下降原因。",
        "clarification": None,
        "intent": None,
    }
    assert result.attempts == {"model_attempts": 1}


def test_planner_keeps_llm_clarification_decision():
    service = FakePlanningService(
        decision=PlannerDecision(
            action="needs_clarification",
            route=None,
            reason="缺少分析范围。",
            clarification_question="请补充区域、时间范围和需要分析的指标。",
            response_message=None,
            resolved_question=None,
            clarification={"missing_slots": ["region", "time_range"], "examples": []},
        )
    )
    agent = PlannerAgent(planning_service=service)

    result = agent.run(AgentInput(question="帮我分析一下", user_id=1))

    assert result.success is True
    assert result.plan is not None
    assert result.plan["action"] == "needs_clarification"
    assert result.plan["route"] is None


def test_planner_returns_failure_when_llm_output_is_invalid():
    service = FakePlanningService(
        error=StructuredOutputError("模型输出不是合法的 Planner JSON")
    )
    agent = PlannerAgent(planning_service=service)
    result = agent.run(AgentInput(question="华东区销售额是多少", user_id=1))

    assert result.success is False
    assert result.error is not None
    assert "无法生成 Planner 决策" in result.error
    assert result.error_code == "planner_invalid_output"
    assert result.retryable is False
    assert result.attempts == {"model_attempts": 1}


def test_planner_marks_transient_model_errors_as_retryable():
    service = FakePlanningService(error=RetryableModelError("模型服务超时"))
    agent = PlannerAgent(planning_service=service)

    result = agent.run(AgentInput(question="华东区销售额是多少", user_id=1))

    assert result.success is False
    assert result.error_code == "planner_model_retryable_error"
    assert result.retryable is True
    assert result.attempts == {"model_attempts": 1}


def test_reviewer_agent_interface():
    agent = ReviewerAgent()
    assert agent.name == "reviewer"
    assert len(agent.description) > 0
    assert len(agent.allowed_tools) == 0


def test_reviewer_agent_rejects_empty_context():
    agent = ReviewerAgent()
    result = agent.run(
        AgentInput(
            question="测试",
            user_id=1,
            context={},
        )
    )
    assert result.success is False
    assert (
        result.error
        == "ReviewerAgent 需要 context 中有 data_result 或 knowledge_result"
    )


def test_reviewer_reports_data_but_refuses_unsupported_cause():
    agent = ReviewerAgent()

    result = agent.run(
        AgentInput(
            question="华东区销售额为什么下降？",
            user_id=1,
            context={
                "data_result": {
                    "evidence": [
                        {
                            "purpose": "计算华东区销售额变化",
                            "columns": ["change"],
                            "rows": [(-166405.92,)],
                        }
                    ]
                },
                "knowledge_result": {
                    "answer": "无法回答：资料不足",
                    "evidences": [],
                },
            },
        )
    )

    assert result.success is True
    assert result.answer is not None
    assert "-166405.92" in result.answer
    assert "无法根据现有文档说明下降原因" in result.answer
    assert result.evidence[0]["review_status"] == "partial"


def test_reviewer_marks_successful_data_only_query_as_completed():
    agent = ReviewerAgent()

    result = agent.run(
        AgentInput(
            question="华东区销售额是多少？",
            user_id=1,
            context={
                "data_result": {
                    "evidence": [
                        {
                            "purpose": "查询华东区销售额",
                            "columns": ["revenue"],
                            "rows": [(1847604.72,)],
                        }
                    ]
                },
                "knowledge_result": None,
                "plan": {"route": "data_only"},
            },
        )
    )

    assert result.success is True
    assert result.answer is not None
    assert "1847604.72" in result.answer
    assert "无法根据现有文档说明下降原因" not in result.answer
    assert result.evidence[0]["review_status"] == "completed"


def test_reviewer_model_hides_data_that_does_not_support_the_question():
    semantic_reviewer = FakeSemanticReviewer(
        evidence_review=EvidenceSemanticReview(
            verdict="unsupported",
            reason="客户编号不能支持广告点击率。",
            limitations=["缺少广告曝光量和点击量。"],
        )
    )
    agent = ReviewerAgent(semantic_reviewer=semantic_reviewer)

    result = agent.run(
        AgentInput(
            question="本月广告点击率是多少？",
            user_id=1,
            context={
                "semantic_review_enabled": True,
                "plan": {"route": "data_only"},
                "data_result": {
                    "status": "ready",
                    "evidence": [
                        {
                            "purpose": "查询客户编号",
                            "columns": ["客户编号"],
                            "rows": [[1]],
                        }
                    ],
                },
                "knowledge_result": {},
            },
        )
    )

    assert result.success is True
    assert "客户编号为1" not in (result.answer or "")
    assert result.evidence[0]["review_status"] == "partial"
    assert result.evidence[0]["report"]["status"] == "partial"


def test_reviewer_returns_partial_when_document_retrieval_failed():
    agent = ReviewerAgent()

    result = agent.run(
        AgentInput(
            question="华东区销售额为什么下降？",
            user_id=1,
            context={
                "plan": {"route": "hybrid"},
                "data_result": {
                    "status": "ready",
                    "evidence": [
                        {
                            "purpose": "查询华东区销售额",
                            "columns": ["revenue"],
                            "rows": [[1847604.72]],
                        }
                    ],
                },
                "knowledge_result": {
                    "status": "failed",
                    "error": "文档检索暂时不可用",
                },
            },
        )
    )

    assert result.success is True
    assert result.evidence[0]["review_status"] == "partial"
    assert result.evidence[0]["data_available"] is True
    assert result.evidence[0]["knowledge_available"] is False
    assert "文档检索暂时不可用" in result.evidence[0]["limitations"][0]


def test_reviewer_returns_partial_when_only_document_evidence_is_available():
    agent = ReviewerAgent()

    result = agent.run(
        AgentInput(
            question="华东区销售额为什么下降？",
            user_id=1,
            context={
                "plan": {"route": "hybrid"},
                "data_result": {
                    "status": "failed",
                    "error": "经营数据查询失败",
                },
                "knowledge_result": {
                    "status": "ready",
                    "answer": "客户合同到期后尚未续约。",
                    "evidences": [
                        {
                            "chunk_id": 42,
                            "document_id": 5,
                            "content": "客户合同到期后尚未续约。",
                            "score": 0.93,
                        }
                    ],
                },
            },
        )
    )

    assert result.success is True
    assert "尚未由当前经营数据验证" in result.answer
    assert result.evidence[0]["review_status"] == "partial"
    assert result.evidence[0]["data_available"] is False
    assert result.evidence[0]["knowledge_available"] is True


def test_reviewer_prioritizes_data_insufficiency_over_uncited_knowledge_text():
    agent = ReviewerAgent()

    result = agent.run(
        AgentInput(
            question="本月广告点击率是多少？",
            user_id=1,
            context={
                "plan": {"route": "hybrid"},
                "data_result": {
                    "status": "insufficient_evidence",
                    "error": "当前快照没有广告曝光量和点击量。",
                },
                "knowledge_result": {
                    "status": "ready",
                    "answer": "这是一段没有引用的文本。",
                    "evidences": [],
                },
            },
        )
    )

    assert result.success is True
    assert "广告曝光量和点击量" in (result.answer or "")
    assert "没有引用的文本" not in (result.answer or "")


def test_planner_passes_conversation_context_to_planning_service():
    context = {
        "version": "1.0",
        "messages": [
            {
                "id": 101,
                "role": "user",
                "content": "先分析华东区 7 月销售额。",
                "content_truncated": False,
            }
        ],
        "history_truncated": False,
    }
    service = FakePlanningService(
        decision=PlannerDecision(
            action="analyze",
            route="data_only",
            reason="上下文已补足范围。",
            clarification_question=None,
            response_message=None,
            resolved_question="分析华东区 7 月销售额。",
        )
    )
    agent = PlannerAgent(planning_service=service)

    result = agent.run(
        AgentInput(
            question="那这个月呢？",
            user_id=1,
            context={"conversation_context": context},
        )
    )

    assert result.success is True
    assert service.questions == ["那这个月呢？"]
    assert service.conversation_contexts == [context]


def test_reviewer_returns_structured_failed_report_when_sources_both_failed():
    agent = ReviewerAgent()

    result = agent.run(
        AgentInput(
            question="华东区销售额为什么下降？",
            user_id=1,
            context={
                "data_result": {"status": "failed", "error": "数据查询失败"},
                "knowledge_result": {"status": "failed", "error": "文档检索失败"},
            },
        )
    )

    assert result.success is True
    assert result.evidence[0]["review_status"] == "failed"
    assert result.evidence[0]["report"]["status"] == "failed"


def test_reviewer_returns_failed_report_when_data_failed_and_document_evidence_is_insufficient():
    agent = ReviewerAgent()

    result = agent.run(
        AgentInput(
            question="华东区销售额为什么下降？",
            user_id=1,
            context={
                "data_result": {
                    "status": "failed",
                    "error": "经营数据查询失败",
                },
                "knowledge_result": {
                    "status": "insufficient_evidence",
                    "answer": "无法回答：资料不足",
                    "evidences": [],
                },
            },
        )
    )

    assert result.success is True
    assert result.evidence[0]["report"]["status"] == "failed"


def test_reviewer_combines_data_and_document_evidence():
    agent = ReviewerAgent()

    result = agent.run(
        AgentInput(
            question="华东区销售额为什么下降？",
            user_id=1,
            context={
                "data_result": {
                    "evidence": [
                        {
                            "purpose": "计算华东区销售额变化",
                            "columns": ["change"],
                            "rows": [(-166405.92,)],
                        }
                    ]
                },
                "knowledge_result": {
                    "answer": "客户年度合同到期后未续约。",
                    "evidences": [{"chunk_id": 42}],
                },
            },
        )
    )

    assert result.success is True
    assert result.answer is not None
    assert "-166405.92" in result.answer
    assert "客户年度合同到期后未续约。" in result.answer
    assert "[引用:42]" in result.answer
    assert result.evidence[0]["review_status"] == "complete"
    assert result.evidence[0]["citation_chunk_ids"] == [42]
    report = result.evidence[0]["report"]
    assert report["status"] == "completed"
    assert report["confirmed_facts"][0]["data_evidence_ids"] == ["data-1"]
    assert report["hypotheses"][0]["citation_chunk_ids"] == [42]
    assert report["recommendations"][0]["basis_fact_ids"] == ["fact-1"]
