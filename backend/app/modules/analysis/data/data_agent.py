"""Data Agent —— 生成候选 SQL，并通过受控 SQL Tool 查询经营数据。"""

from datetime import date
from decimal import Decimal

from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.modules.analysis.agent_protocol import Agent, AgentInput, AgentOutput
from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
from app.modules.analysis.data.query_contract import QueryContract
from app.modules.analysis.data.query_validation import assess_query_result
from app.modules.analysis.data.sql_generation import SQLGenerationService
from app.modules.analysis.data.sql_tool import SQLTool
from app.modules.analysis.metrics.claim_validation import assess_numeric_assertion
from app.modules.analysis.metrics.metric_validation import assess_metric_query
from app.modules.analysis.planner.planner_decision import EvaluationScope
from app.modules.analysis.tool_protocol import Tool, ToolInput
from app.modules.organizations.models import BusinessDataSource
from app.modules.reporting.semantic_review_service import SemanticReviewService
from pydantic import ValidationError

MAX_DATA_ATTEMPTS = 2


def _concept_key(value: object) -> str:
    """Normalize only common measurement suffixes, not arbitrary business meaning."""
    text = str(value).strip().replace(" ", "")
    for suffix in ("计数", "总数", "数量", "金额", "数值", "量"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)]
    return text


def _make_json_safe(value):
    if isinstance(value, Decimal):
        return format(value, "f")

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, (list, tuple)):
        return [_make_json_safe(item) for item in value]

    return value


def _validated_evaluation_scope(plan: object) -> dict[str, object] | None:
    if not isinstance(plan, dict) or not isinstance(plan.get("evaluation_scope"), dict):
        return None
    try:
        scope = EvaluationScope.model_validate(plan["evaluation_scope"])
    except ValidationError:
        return None
    if not scope.entities and scope.period is None:
        return None
    return scope.model_dump()


class DataAgent(Agent):
    """只使用受控 SQL 生成服务和只读 SQL Tool 的 Agent。"""

    def __init__(
        self,
        sql_generator: SQLGenerationService | None = None,
        sql_tool: Tool | None = None,
        *,
        data_source: BusinessDataSource | None = None,
        snapshot_catalog: SnapshotCatalog | None = None,
        semantic_reviewer: SemanticReviewService | None = None,
    ) -> None:
        if (data_source is None) != (snapshot_catalog is None):
            raise ValueError("公司数据源和 schema snapshot 必须同时提供")
        self._sql_generator = sql_generator
        self._snapshot_catalog = snapshot_catalog
        self._semantic_reviewer = semantic_reviewer
        self._sql_tool = sql_tool or SQLTool(
            data_source=data_source,
            snapshot_catalog=snapshot_catalog,
        )

    @property
    def name(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return "生成受控候选 SQL，并查询经营数据库中的指标数据"

    @property
    def allowed_tools(self) -> list[Tool]:
        return [self._sql_tool]

    def run(self, input: AgentInput) -> AgentOutput:
        feedback = input.context.get("feedback") or {}
        if (
            feedback.get("target") == "data"
            and feedback.get("mode") == "replay_validated_sql"
            and isinstance(feedback.get("previous_sql"), str)
        ):
            return self._replay_validated_sql(feedback)
        if self._sql_generator is None:
            self._sql_generator = SQLGenerationService(catalog=self._snapshot_catalog)

        repair_reason = None
        previous_sql = None
        plan = input.context.get("plan")
        evaluation_scope = _validated_evaluation_scope(plan)
        intent = plan.get("intent") if isinstance(plan, dict) else None
        required_capabilities = (
            [
                item
                for item in intent.get("required_capabilities", [])
                if isinstance(item, str)
            ]
            if isinstance(intent, dict)
            else []
        )
        data_required_capabilities = [
            item for item in required_capabilities if item != "document_evidence"
        ]
        attempts = {
            "model_attempts": 0,
            "sql_attempts": 0,
        }

        for attempt_index in range(MAX_DATA_ATTEMPTS):
            try:
                attempts["model_attempts"] += 1
                candidate = self._sql_generator.generate(
                    input.question,
                    repair_reason=repair_reason,
                    previous_sql=previous_sql,
                    required_concepts=data_required_capabilities or None,
                    evaluation_scope=evaluation_scope,
                )
            except PermanentModelError as error:
                return AgentOutput(
                    success=False,
                    attempts=attempts,
                    error=f"无法生成受控 SQL: {error}",
                    error_code="sql_generation_permanent_error",
                )
            except RetryableModelError:
                if attempt_index == MAX_DATA_ATTEMPTS - 1:
                    return AgentOutput(
                        success=False,
                        attempts=attempts,
                        error="经营数据 SQL 生成暂时无法完成。",
                        error_code="sql_generation_retryable_error",
                    )
                repair_reason = "sql_generation_retryable_error"
                previous_sql = None
                continue
            except StructuredOutputError:
                if attempt_index == MAX_DATA_ATTEMPTS - 1:
                    return AgentOutput(
                        success=False,
                        attempts=attempts,
                        error="经营数据 SQL 生成结果不符合要求。",
                        error_code="sql_generation_invalid_output",
                    )
                repair_reason = "sql_generation_invalid_output"
                previous_sql = None
                continue

            if input.context.get("semantic_review_enabled"):
                if candidate.query_contract is None:
                    return AgentOutput(
                        success=False,
                        attempts=attempts,
                        error="SQL 候选缺少可验证的查询结果契约。",
                        error_code="query_contract_missing",
                        evidence=[
                            {
                                "sql": candidate.sql,
                                "purpose": candidate.purpose,
                            }
                        ],
                    )
                if isinstance(intent, dict):
                    required = {
                        _concept_key(item) for item in data_required_capabilities
                    }
                    declared = {
                        _concept_key(item)
                        for item in candidate.query_contract.required_concepts
                    }
                    missing = sorted(required - declared)
                    if missing:
                        return AgentOutput(
                            success=False,
                            attempts=attempts,
                            error="查询契约没有覆盖规划所需的业务能力："
                            + "、".join(missing),
                            error_code="query_contract_incomplete",
                            evidence=[
                                {
                                    "sql": candidate.sql,
                                    "purpose": candidate.purpose,
                                    "missing_requirements": missing,
                                }
                            ],
                        )
                    unexpected = sorted(declared - required)
                    if unexpected:
                        return AgentOutput(
                            success=False,
                            attempts=attempts,
                            error="查询契约包含规划未要求的业务能力："
                            + "、".join(unexpected),
                            error_code="query_contract_out_of_scope",
                            evidence=[
                                {
                                    "sql": candidate.sql,
                                    "purpose": candidate.purpose,
                                    "unexpected_requirements": unexpected,
                                }
                            ],
                        )
                attempts.setdefault("semantic_review_attempts", 0)
                if self._semantic_reviewer is None:
                    self._semantic_reviewer = SemanticReviewService()
                try:
                    semantic_review = self._semantic_reviewer.review_sql(
                        question=input.question,
                        plan=input.context.get("plan") or {},
                        candidate=candidate,
                        catalog=self._snapshot_catalog,
                    )
                    attempts["semantic_review_attempts"] += 1
                except (
                    PermanentModelError,
                    RetryableModelError,
                    StructuredOutputError,
                ) as error:
                    return AgentOutput(
                        success=False,
                        attempts=attempts,
                        error=f"SQL 语义复核未能完成: {error}",
                        error_code="sql_semantic_review_failed",
                    )

                if semantic_review.decision == "insufficient_schema":
                    return AgentOutput(
                        success=False,
                        attempts=attempts,
                        error=semantic_review.reason,
                        error_code="insufficient_schema",
                        evidence=[
                            {
                                "sql": candidate.sql,
                                "purpose": candidate.purpose,
                                "missing_requirements": semantic_review.missing_requirements,
                            }
                        ],
                    )
                if semantic_review.decision == "repair":
                    if attempt_index < MAX_DATA_ATTEMPTS - 1:
                        repair_reason = "sql_semantic_error"
                        previous_sql = candidate.sql
                        continue
                    return AgentOutput(
                        success=False,
                        attempts=attempts,
                        error=semantic_review.reason,
                        error_code="sql_semantic_unsupported",
                        evidence=[
                            {
                                "sql": candidate.sql,
                                "purpose": candidate.purpose,
                                "missing_requirements": semantic_review.missing_requirements,
                            }
                        ],
                    )

            metric_assessment = assess_metric_query(
                candidate.sql,
                candidate.query_contract,
                evaluation_scope=evaluation_scope,
            )
            if (
                input.context.get("semantic_review_enabled")
                and metric_assessment.status != "supported"
            ):
                if attempt_index < MAX_DATA_ATTEMPTS - 1:
                    repair_reason = "metric_contract_" + metric_assessment.status
                    previous_sql = candidate.sql
                    continue
                return AgentOutput(
                    success=False,
                    attempts=attempts,
                    error=metric_assessment.reason,
                    error_code="metric_contract_" + metric_assessment.status,
                    evidence=[
                        {
                            "sql": candidate.sql,
                            "purpose": candidate.purpose,
                            "metric_assessment": {
                                "status": metric_assessment.status,
                                "reason": metric_assessment.reason,
                            },
                        }
                    ],
                )

            attempts["sql_attempts"] += 1
            result = self._sql_tool.execute(
                ToolInput(parameters={"sql": candidate.sql})
            )

            if result.success:
                columns = result.data.get("columns") if result.data else []
                rows = result.data.get("rows") if result.data else []
                assessment = assess_query_result(
                    columns=columns,
                    rows=rows,
                    contract=candidate.query_contract,
                )
                claim_assessment = assess_numeric_assertion(
                    candidate.query_contract.numeric_assertion
                    if candidate.query_contract is not None
                    else None,
                    columns=columns,
                    rows=rows,
                    metric_status=metric_assessment.status,
                )
                metric_definition = metric_assessment.definition
                evidence = {
                    "sql": candidate.sql,
                    "purpose": candidate.purpose,
                    "query_contract": (
                        candidate.query_contract.model_dump()
                        if candidate.query_contract is not None
                        else None
                    ),
                    "columns": columns,
                    "rows": _make_json_safe(rows),
                    "result_assessment": assessment.model_dump(),
                    "claim_assessment": {
                        "status": claim_assessment.status,
                        "reason": claim_assessment.reason,
                    },
                    "metric_assessment": {
                        "status": metric_assessment.status,
                        "reason": metric_assessment.reason,
                        "metric_definition_ref": (
                            metric_definition.reference if metric_definition else None
                        ),
                        "unit": metric_definition.unit if metric_definition else None,
                        "time_column": (
                            metric_definition.time_column if metric_definition else None
                        ),
                        "time_semantics": (
                            metric_definition.time_semantics
                            if metric_definition
                            else None
                        ),
                        "lineage_columns": list(metric_assessment.lineage_columns),
                    },
                }
                if assessment.status != "supported":
                    return AgentOutput(
                        success=False,
                        attempts=attempts,
                        error=assessment.reason,
                        error_code=assessment.status,
                        evidence=[evidence],
                    )
                return AgentOutput(
                    success=True,
                    answer=None,
                    attempts=attempts,
                    evidence=[evidence],
                )
            if result.repairable and attempt_index < MAX_DATA_ATTEMPTS - 1:
                repair_reason = result.error_code or "sql_validation_error"
                previous_sql = candidate.sql
                continue

            return AgentOutput(
                success=False,
                attempts=attempts,
                error=result.error or "经营数据查询失败。",
                error_code=result.error_code,
                evidence=[
                    {
                        "sql": candidate.sql,
                        "purpose": candidate.purpose,
                        "query_contract": (
                            candidate.query_contract.model_dump()
                            if candidate.query_contract is not None
                            else None
                        ),
                    }
                ],
            )
        return AgentOutput(
            success=False,
            attempts=attempts,
            error="经营数据查询未能完成。",
            error_code="data_attempt_budget_exhausted",
        )

    def _replay_validated_sql(self, feedback: dict) -> AgentOutput:
        """Retry only a SQL statement that previously passed the SQL Tool boundary."""
        sql = feedback["previous_sql"]
        attempts = {"model_attempts": 0, "sql_attempts": 1, "replayed_sql": 1}
        purpose = feedback.get("purpose") or "重试已验证经营数据查询"
        contract_data = feedback.get("query_contract")
        contract = (
            QueryContract.model_validate(contract_data)
            if isinstance(contract_data, dict)
            else None
        )
        metric_assessment = assess_metric_query(sql, contract)
        if (
            contract is not None
            and contract.metric_definition_ref is not None
            and metric_assessment.status != "supported"
        ):
            return AgentOutput(
                success=False,
                attempts=attempts,
                error=metric_assessment.reason,
                error_code="metric_contract_" + metric_assessment.status,
            )
        result = self._sql_tool.execute(ToolInput(parameters={"sql": sql}))
        if result.success:
            columns = result.data.get("columns") if result.data else []
            rows = result.data.get("rows") if result.data else []
            assessment = assess_query_result(
                columns=columns,
                rows=rows,
                contract=contract,
            )
            claim_assessment = assess_numeric_assertion(
                contract.numeric_assertion if contract is not None else None,
                columns=columns,
                rows=rows,
                metric_status=metric_assessment.status,
            )
            metric_definition = metric_assessment.definition
            evidence = {
                "sql": sql,
                "purpose": purpose,
                "query_contract": contract.model_dump() if contract else None,
                "columns": columns,
                "rows": _make_json_safe(rows),
                "result_assessment": assessment.model_dump(),
                "claim_assessment": {
                    "status": claim_assessment.status,
                    "reason": claim_assessment.reason,
                },
                "metric_assessment": {
                    "status": metric_assessment.status,
                    "reason": metric_assessment.reason,
                    "metric_definition_ref": (
                        metric_definition.reference if metric_definition else None
                    ),
                    "unit": metric_definition.unit if metric_definition else None,
                    "time_column": (
                        metric_definition.time_column if metric_definition else None
                    ),
                    "time_semantics": (
                        metric_definition.time_semantics if metric_definition else None
                    ),
                    "lineage_columns": list(metric_assessment.lineage_columns),
                },
            }
            if assessment.status == "supported":
                return AgentOutput(success=True, attempts=attempts, evidence=[evidence])
            return AgentOutput(
                success=False,
                attempts=attempts,
                error=assessment.reason,
                error_code=assessment.status,
                evidence=[evidence],
            )
        return AgentOutput(
            success=False,
            attempts=attempts,
            error=result.error or "经营数据查询失败。",
            error_code=result.error_code,
            evidence=[
                {"sql": sql, "purpose": purpose, "query_contract": contract_data}
            ],
        )
