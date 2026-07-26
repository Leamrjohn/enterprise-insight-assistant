from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.query_contract import ClarificationSpec, QuestionIntent


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

        if self.action not in terminal_actions and self.response_message is not None:
            raise ValueError("only terminal actions may include response_message")

        return self
