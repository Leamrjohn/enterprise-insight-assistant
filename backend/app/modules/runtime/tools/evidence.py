"""T3c: what each tool returns, and the one Evidence shape every node will read.

Output models check structure only; they allow extra fields so a result that
carries a flag such as "degraded" still passes.  Validation never rewrites the
result: the tool's own data is what the agents receive today.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _Output(BaseModel):
    model_config = ConfigDict(extra="allow")


class SQLQueryOutput(_Output):
    columns: list[str]
    rows: list[list[Any]]  # tuples from the driver validate as lists


class TemplateQueryOutput(SQLQueryOutput):
    query_id: str
    parameters: dict[str, Any]


class _Chunk(_Output):
    chunk_id: int
    document_id: int | None = None
    content: str
    score: float | None = None


class RAGSearchOutput(_Output):
    status: Literal["ready", "insufficient_evidence"]
    evidences: list[_Chunk]


class Evidence(BaseModel):
    """One piece of evidence: a result table, or one passage of a document."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["table", "document"]
    source_tool: str
    columns: list[str] = []
    rows: list[list[Any]] = []
    document_id: int | None = None
    chunk_id: int | None = None
    excerpt: str | None = None
    score: float | None = None


def sql_query_evidence(output: SQLQueryOutput) -> list[Evidence]:
    return [
        Evidence(
            kind="table",
            source_tool="sql_query",
            columns=output.columns,
            rows=output.rows,
        )
    ]


def template_query_evidence(output: TemplateQueryOutput) -> list[Evidence]:
    return [
        Evidence(
            kind="table",
            source_tool="template_query",
            columns=output.columns,
            rows=output.rows,
        )
    ]


def rag_search_evidence(output: RAGSearchOutput) -> list[Evidence]:
    return [
        Evidence(
            kind="document",
            source_tool="rag_search",
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            excerpt=chunk.content,
            score=chunk.score,
        )
        for chunk in output.evidences
    ]
