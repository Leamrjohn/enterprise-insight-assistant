"""Planner Agent 的受控输出契约。"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


AnalysisRoute = Literal[
    "data_only",
    "knowledge_only",
    "hybrid",
    "clarify",
]


class AnalysisPlan(BaseModel):
    """决定工作流的执行路径。"""

    route: AnalysisRoute
    reason: str = Field(min_length=1)

    # 暂时保留：现有 Graph 仍会读取它们。
    need_knowledge: bool
    need_data: bool

    @model_validator(mode="after")
    def route_matches_requested_sources(self) -> "AnalysisPlan":
        expected_sources = {
            "data_only": (True, False),
            "knowledge_only": (False, True),
            "hybrid": (True, True),
            "clarify": (False, False),
        }
        expected_data, expected_knowledge = expected_sources[self.route]

        if (
            self.need_data != expected_data
            or self.need_knowledge != expected_knowledge
        ):
            raise ValueError(
                "route must match need_data and need_knowledge"
            )
        return self
