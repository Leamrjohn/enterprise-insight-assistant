from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FailureDetail(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    component: Literal["data", "knowledge", "planner"]
    reason: str = Field(min_length=1)
    impact: str = Field(min_length=1)


class Hypothesis(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    statement: str = Field(min_length=1)
    basis: list[str] = Field(min_length=1)


class FinalAnalysis(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    status: Literal["completed", "partial", "failed"]
    answer: str = Field(min_length=1)
    data_preview: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    analysis_summary: str = Field(min_length=1)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    failures: list[FailureDetail] = Field(default_factory=list)
    next_steps: list[str] = Field(min_length=1)
    citation_chunk_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_contract(self) -> "FinalAnalysis":
        has_facts = bool(self.data_preview or self.confirmed_facts)

        if self.status == "completed":
            if not has_facts:
                raise ValueError("completed 状态必须包含已确认事实")
            if self.failures:
                raise ValueError("completed 状态不能包含失败原因")

        if self.status == "partial":
            if not has_facts:
                raise ValueError("partial 状态必须包含至少一条已确认事实")
            if not self.failures:
                raise ValueError("partial 状态必须说明失败或证据不足原因")

        if self.status == "failed":
            if not self.failures:
                raise ValueError("failed 状态必须包含失败原因")
            if has_facts:
                raise ValueError("failed 状态不能包含已确认事实")
            if self.hypotheses:
                raise ValueError("没有事实时不能生成推测")

        if self.hypotheses and not has_facts:
            raise ValueError("推测必须建立在至少一条已确认事实上")

        return self
