"""Persistable, evidence-bound contract for a business analysis response."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfirmedFact(BaseModel):
    fact_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    data_evidence_ids: list[str] = Field(min_length=1)


class Hypothesis(BaseModel):
    hypothesis_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    related_fact_ids: list[str] = Field(min_length=1)
    citation_chunk_ids: list[int] = Field(min_length=1)
    support_level: Literal["low", "medium", "high"]


class Recommendation(BaseModel):
    recommendation_id: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    basis_fact_ids: list[str] = Field(default_factory=list)
    basis_hypothesis_ids: list[str] = Field(default_factory=list)
    verification_metric: str | None = None

    @model_validator(mode="after")
    def requires_a_basis(self) -> "Recommendation":
        if not self.basis_fact_ids and not self.basis_hypothesis_ids:
            raise ValueError("建议必须关联至少一条事实或假设")
        return self


class DataEvidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    sql: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[object]] = Field(default_factory=list)


class DocumentCitation(BaseModel):
    chunk_id: int
    document_id: int | None = None
    excerpt: str = Field(min_length=1)
    score: float | None = None


class Limitation(BaseModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    next_step: str = Field(min_length=1)


class FinalAnalysisReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: Literal["completed", "partial", "failed"]
    executive_summary: str = Field(min_length=1)
    confirmed_facts: list[ConfirmedFact] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    data_evidence: list[DataEvidence] = Field(default_factory=list)
    document_citations: list[DocumentCitation] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_contract(self) -> "FinalAnalysisReport":
        fact_ids = {fact.fact_id for fact in self.confirmed_facts}
        data_evidence_ids = {evidence.evidence_id for evidence in self.data_evidence}
        citation_ids = {citation.chunk_id for citation in self.document_citations}

        for fact in self.confirmed_facts:
            if not set(fact.data_evidence_ids).issubset(data_evidence_ids):
                raise ValueError("事实必须关联已有数据证据")
        for hypothesis in self.hypotheses:
            if not set(hypothesis.related_fact_ids).issubset(fact_ids):
                raise ValueError("假设必须关联已有确认事实")
            if not set(hypothesis.citation_chunk_ids).issubset(citation_ids):
                raise ValueError("假设必须关联已有文档引用")
        for recommendation in self.recommendations:
            if not set(recommendation.basis_fact_ids).issubset(fact_ids):
                raise ValueError("建议关联了不存在的事实")
            hypothesis_ids = {
                hypothesis.hypothesis_id for hypothesis in self.hypotheses
            }
            if not set(recommendation.basis_hypothesis_ids).issubset(hypothesis_ids):
                raise ValueError("建议关联了不存在的假设")

        if self.status == "completed":
            if not self.confirmed_facts:
                raise ValueError("completed 状态必须包含确认事实")
            if self.limitations:
                raise ValueError("completed 状态不能包含限制")
        if self.status == "partial" and not self.limitations:
            raise ValueError("partial 状态必须说明资料或执行限制")
        if self.status == "failed":
            if self.confirmed_facts or self.hypotheses or self.recommendations:
                raise ValueError("failed 状态不能包含分析结论")
            if not self.limitations:
                raise ValueError("failed 状态必须说明失败原因")
        return self
