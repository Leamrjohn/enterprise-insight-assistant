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
    citation_chunk_ids: list[int] = Field(default_factory=list)
    attachment_citation_ids: list[str] = Field(default_factory=list)
    support_level: Literal["low", "medium", "high"]

    @model_validator(mode="after")
    def requires_document_or_attachment_evidence(self) -> "Hypothesis":
        if not self.citation_chunk_ids and not self.attachment_citation_ids:
            raise ValueError("假设必须关联至少一条文档或附件引用")
        return self


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
    metric_assessment: "MetricAssessment | None" = None
    claim_assessment: "ClaimAssessment | None" = None


class MetricAssessment(BaseModel):
    status: Literal["supported", "insufficient", "irrelevant"]
    reason: str = Field(min_length=1)
    metric_definition_ref: str | None = None
    unit: Literal["CNY", "count"] | None = None
    time_column: str | None = None
    time_semantics: Literal["business_calendar_date"] | None = None
    lineage_columns: list[str] = Field(default_factory=list)


class ClaimAssessment(BaseModel):
    status: Literal["supported", "refuted", "insufficient", "irrelevant"]
    reason: str = Field(min_length=1)


class DocumentCitation(BaseModel):
    chunk_id: int
    document_id: int | None = None
    excerpt: str = Field(min_length=1)
    score: float | None = None


class DocumentQualification(BaseModel):
    """A verbatim, citation-bound boundary on a document finding."""

    statement: str = Field(min_length=1)
    citation_chunk_ids: list[int] = Field(min_length=1)


class DocumentFinding(BaseModel):
    """A directly supported document fact, distinct from a data-backed fact."""

    finding_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    citation_chunk_ids: list[int] = Field(min_length=1)
    qualifications: list[DocumentQualification] = Field(default_factory=list)


def build_attachment_citation_id(
    *,
    artifact_version_id: int,
    parse_result_id: int,
    char_start: int,
    char_end: int,
    fragment_sha256: str,
) -> str:
    """Return the deterministic identity for one immutable parsed-text span."""
    return (
        f"artifact:{artifact_version_id}:{parse_result_id}:"
        f"{char_start}:{char_end}:{fragment_sha256}"
    )


class AttachmentCitation(BaseModel):
    """A storage-verifiable attachment span; extracted text is never persisted here."""

    citation_id: str = Field(min_length=1, max_length=256)
    artifact_version_id: int = Field(gt=0)
    parse_result_id: int = Field(gt=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    fragment_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validates_identity_and_range(self) -> "AttachmentCitation":
        if self.char_end <= self.char_start:
            raise ValueError("附件引用的字符范围必须为非空区间")
        expected_id = build_attachment_citation_id(
            artifact_version_id=self.artifact_version_id,
            parse_result_id=self.parse_result_id,
            char_start=self.char_start,
            char_end=self.char_end,
            fragment_sha256=self.fragment_sha256,
        )
        if self.citation_id != expected_id:
            raise ValueError("附件引用标识与版本、范围或哈希不匹配")
        return self


class Limitation(BaseModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    next_step: str = Field(min_length=1)


class FinalAnalysisReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    schema_version: Literal["1.0", "1.1", "1.2"] = "1.2"
    status: Literal["completed", "partial", "failed"]
    executive_summary: str = Field(min_length=1)
    confirmed_facts: list[ConfirmedFact] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    data_evidence: list[DataEvidence] = Field(default_factory=list)
    document_citations: list[DocumentCitation] = Field(default_factory=list)
    document_findings: list[DocumentFinding] = Field(default_factory=list)
    attachment_citations: list[AttachmentCitation] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_contract(self) -> "FinalAnalysisReport":
        fact_ids = {fact.fact_id for fact in self.confirmed_facts}
        data_evidence_ids = {evidence.evidence_id for evidence in self.data_evidence}
        citation_ids = {citation.chunk_id for citation in self.document_citations}
        attachment_citation_ids = {
            citation.citation_id for citation in self.attachment_citations
        }
        if len(attachment_citation_ids) != len(self.attachment_citations):
            raise ValueError("附件引用不能重复")
        if self.attachment_citations and self.schema_version not in {"1.1", "1.2"}:
            raise ValueError("附件引用只能出现在 schema_version 1.1 或 1.2 的报告中")

        for fact in self.confirmed_facts:
            if not set(fact.data_evidence_ids).issubset(data_evidence_ids):
                raise ValueError("事实必须关联已有数据证据")
        for hypothesis in self.hypotheses:
            if not set(hypothesis.related_fact_ids).issubset(fact_ids):
                raise ValueError("假设必须关联已有确认事实")
            if not set(hypothesis.citation_chunk_ids).issubset(citation_ids):
                raise ValueError("假设必须关联已有文档引用")
            if not set(hypothesis.attachment_citation_ids).issubset(
                attachment_citation_ids
            ):
                raise ValueError("假设必须关联已有附件引用")
        for finding in self.document_findings:
            if not set(finding.citation_chunk_ids).issubset(citation_ids):
                raise ValueError("文档事实必须关联已有文档引用")
            for qualification in finding.qualifications:
                if not set(qualification.citation_chunk_ids).issubset(citation_ids):
                    raise ValueError("文档限定语必须关联已有文档引用")
        for recommendation in self.recommendations:
            if not set(recommendation.basis_fact_ids).issubset(fact_ids):
                raise ValueError("建议关联了不存在的事实")
            hypothesis_ids = {
                hypothesis.hypothesis_id for hypothesis in self.hypotheses
            }
            if not set(recommendation.basis_hypothesis_ids).issubset(hypothesis_ids):
                raise ValueError("建议关联了不存在的假设")

        if self.status == "completed":
            if not self.confirmed_facts and not self.document_findings:
                raise ValueError("completed 状态必须包含确认事实或文档事实")
            if self.limitations:
                raise ValueError("completed 状态不能包含限制")
        if self.status == "partial" and not self.limitations:
            raise ValueError("partial 状态必须说明资料或执行限制")
        if self.status == "failed":
            if (
                self.confirmed_facts
                or self.hypotheses
                or self.document_findings
                or self.recommendations
            ):
                raise ValueError("failed 状态不能包含分析结论")
            if not self.limitations:
                raise ValueError("failed 状态必须说明失败原因")
        return self
