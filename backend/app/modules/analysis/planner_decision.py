import re
from typing import Literal

from app.modules.analysis.query_contract import ClarificationSpec, QuestionIntent
from pydantic import BaseModel, Field, model_validator

PlanAction = Literal[
    "analyze",
    "direct_response",
    "scope_exit",
    "needs_clarification",
    "refuse",
]

AnalysisRoute = Literal[
    "data_only",
    "knowledge_only",
    "hybrid",
]

# This deliberately recognizes only explicit document-evidence requests.  It is
# not a general-purpose intent classifier and must not capture causal questions
# that do not expressly ask for document support.
_EXPLICIT_DOCUMENT_EVIDENCE_QUESTION = re.compile(
    r"(?:"
    r"(?:资料|文档)(?:能够|可以)?(?:支持|说明)"
    r"|.+?(?:有)?哪些被(?:资料|文档)(?:支持|说明)(?:的)?(?:因素|事实|结论)?[？?]?"
    r")"
)
_EXPLICIT_SALES_METRIC_REQUEST = re.compile(
    r"(?:请给出|查询|统计|计算).{0,48}销售额|销售额(?:是多少|多少)"
)


class EvaluationScope(BaseModel):
    """The Planner's structured interpretation, not a business fact."""

    entities: list[str] = Field(default_factory=list, max_length=8)
    period: str | None = Field(default=None, min_length=1, max_length=200)


def enforce_explicit_document_evidence_contract(
    question: str, decision: "PlannerDecision"
) -> "PlannerDecision":
    """Keep document-only questions narrow, but preserve explicit data-plus-doc work."""
    if decision.action != "analyze" or not _EXPLICIT_DOCUMENT_EVIDENCE_QUESTION.search(
        question
    ):
        return decision

    specified_slots = (
        decision.intent.specified_slots if decision.intent is not None else []
    )
    if _EXPLICIT_SALES_METRIC_REQUEST.search(question):
        return decision.model_copy(
            update={
                "route": "hybrid",
                "intent": QuestionIntent(
                    kind="document_question",
                    required_capabilities=["销售额", "document_evidence"],
                    specified_slots=specified_slots,
                ),
            }
        )
    return decision.model_copy(
        update={
            "route": "knowledge_only",
            "intent": QuestionIntent(
                kind="document_question",
                required_capabilities=["document_evidence"],
                specified_slots=specified_slots,
            ),
        }
    )


class PlannerDecision(BaseModel):
    action: PlanAction = Field(
        description=(
            "处理动作：analyze 进入分析；direct_response、scope_exit、"
            "needs_clarification、refuse 直接结束工作流。"
        )
    )
    route: AnalysisRoute | None = Field(
        ...,
        description=(
            "分析证据路线；仅 analyze 可选择 data_only、knowledge_only 或 hybrid，"
            "供工作流选择业务 Agent。"
        ),
    )
    reason: str = Field(
        min_length=1,
        max_length=300,
        description="分类的内部理由，用于终态记录和排查，不作为经营结论。",
    )
    clarification_question: str | None = Field(
        ...,
        max_length=300,
        description=(
            "仅 needs_clarification 使用的具体追问；工作流将其返回给用户以补齐分析条件。"
        ),
    )
    response_message: str | None = Field(
        ...,
        max_length=500,
        description=(
            "仅 direct_response、scope_exit、refuse 使用的用户回复；"
            "工作流将其作为无需业务 Agent 的最终回答。"
        ),
    )
    resolved_question: str | None = Field(
        ...,
        min_length=1,
        max_length=1000,
        description=(
            "仅 analyze 使用的独立完整问题；"
            "Data、Knowledge 和 Reviewer 后续使用它，不直接读取会话历史。"
        ),
    )
    clarification: ClarificationSpec | None = Field(
        default=None,
        description="追问所缺的结构化条件；仅 needs_clarification 使用。",
    )
    intent: QuestionIntent | None = Field(
        default=None,
        description="分析问题需要哪些业务能力与条件；仅 analyze 使用。",
    )
    evaluation_scope: EvaluationScope | None = Field(
        default=None,
        description="供评测读取的结构化实体和业务期间；仅 analyze 可填写。",
    )

    @model_validator(mode="after")
    def validate_action_contract(self) -> "PlannerDecision":
        if self.action == "analyze" and self.route is None:
            raise ValueError("analyze action requires route")

        if self.action != "analyze" and self.route is not None:
            raise ValueError("only analyze action may include route")

        if self.action == "analyze" and (
            self.resolved_question is None or not self.resolved_question.strip()
        ):
            raise ValueError("analyze action ,resolved_question must is not none")

        if self.action != "analyze" and self.resolved_question is not None:
            raise ValueError("not analyze action ,resolved_question must is none")

        if self.action == "needs_clarification" and not self.clarification_question:
            raise ValueError("needs_clarification requires clarification_question")

        if self.action == "needs_clarification" and self.clarification is None:
            raise ValueError("needs_clarification requires clarification")

        if self.action != "needs_clarification" and self.clarification is not None:
            raise ValueError("only needs_clarification may include clarification")

        if (
            self.action != "needs_clarification"
            and self.clarification_question is not None
        ):
            raise ValueError(
                "only needs_clarification may include clarification_question"
            )

        terminal_actions = {"direct_response", "scope_exit", "refuse"}
        if self.action in terminal_actions and not self.response_message:
            raise ValueError(f"{self.action} requires response_message")

        if self.action == "analyze" and self.response_message is not None:
            raise ValueError("analyze action must not include response_message")

        if self.action != "analyze" and self.intent is not None:
            raise ValueError("only analyze may include intent")

        if self.action != "analyze" and self.evaluation_scope is not None:
            raise ValueError("only analyze may include evaluation_scope")

        if self.action not in terminal_actions and self.response_message is not None:
            raise ValueError("only terminal actions may include response_message")

        return self
