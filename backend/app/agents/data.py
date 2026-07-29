"""Data Agent —— 生成候选 SQL，并通过受控 SQL Tool 查询经营数据。"""

from app.agents.protocol import Agent, AgentInput, AgentOutput
from app.core.exceptions import (
    PermanentModelError,
    RetryableModelError,
    StructuredOutputError,
)
from app.services.sql_generation import SQLGenerationService
from app.services.semantic_review import SemanticReviewService
from app.services.query_result_validator import assess_query_result
from app.schemas.query_contract import QueryContract
from app.tools.protocol import Tool, ToolInput
from app.tools.sql import SQLTool
from app.models.company import BusinessDataSource
from app.tools.snapshot_catalog import SnapshotCatalog
from decimal import Decimal

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

    if isinstance(value, (list, tuple)):
        return [_make_json_safe(item) for item in value]

    return value


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
                intent = input.context.get("plan", {}).get("intent")
                if isinstance(intent, dict):
                    required = {
                        _concept_key(item)
                        for item in (intent.get("required_capabilities") or [])
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
        result = self._sql_tool.execute(ToolInput(parameters={"sql": sql}))
        purpose = feedback.get("purpose") or "重试已验证经营数据查询"
        contract_data = feedback.get("query_contract")
        contract = (
            QueryContract.model_validate(contract_data)
            if isinstance(contract_data, dict)
            else None
        )
        if result.success:
            columns = result.data.get("columns") if result.data else []
            rows = result.data.get("rows") if result.data else []
            assessment = assess_query_result(
                columns=columns,
                rows=rows,
                contract=contract,
            )
            evidence = {
                "sql": sql,
                "purpose": purpose,
                "query_contract": contract.model_dump() if contract else None,
                "columns": columns,
                "rows": _make_json_safe(rows),
                "result_assessment": assessment.model_dump(),
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
