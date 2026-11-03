"""A reranker outage degrades the search only when the caller allowed it."""

from types import SimpleNamespace

import pytest
from app.modules.analysis.tool_protocol import ToolInput
from app.modules.knowledge import tool as tool_module
from app.modules.knowledge.tool import RAGTool


class _Db:
    def execute(self, *_args, **_kwargs):
        return None

    def close(self):
        pass


def _evidence(chunk_id):
    return SimpleNamespace(
        chunk_id=chunk_id,
        document_id=1,
        content=f"内容{chunk_id}",
        document_name="制度",
        document_type="txt",
        page_number=1,
        paragraph_start=1,
        paragraph_end=1,
        score=0.8,
        rerank_score=None,
        chunk_strategy="s",
        retrieval_strategies=("vector",),
        effective_from=None,
        effective_to=None,
        applies_to=None,
    )


class _Broken:
    def score(self, *_args, **_kwargs):
        raise RuntimeError("reranker down")


@pytest.fixture
def rag(monkeypatch):
    monkeypatch.setattr(tool_module, "SessionLocal", _Db)
    monkeypatch.setattr(tool_module, "set_tenant_scope", lambda *_: None)
    monkeypatch.setattr(tool_module, "LocalEmbeddingProvider", lambda: None)
    monkeypatch.setattr(
        tool_module,
        "retrieve_evidence",
        lambda **_: [_evidence(i) for i in range(1, 6)],
    )
    monkeypatch.setattr(tool_module, "reserve_local_resource_call", lambda **_: None)
    monkeypatch.setattr(tool_module, "record_model_call", lambda *_a, **_k: None)

    def boom(*_args, **_kwargs):
        raise RuntimeError("reranker down")

    monkeypatch.setattr(tool_module, "rerank_evidences", boom)
    monkeypatch.setattr(
        tool_module, "check_sufficiency", lambda evidences, **_: bool(evidences)
    )
    monkeypatch.setattr(
        tool_module,
        "build_prompt",
        lambda question, evidences: ("s", "u", {e.chunk_id for e in evidences}),
    )


def _run(tool):
    return tool.execute(ToolInput(parameters={"question": "q", "company_id": 1}))


def test_without_permission_a_reranker_outage_fails_as_before(rag):
    output = _run(RAGTool(reranker=_Broken()))
    assert not output.success


def test_with_permission_it_keeps_retrieval_order_and_says_it_degraded(rag):
    output = _run(RAGTool(reranker=_Broken(), degrade_on_rerank_failure=True))
    assert output.success
    assert output.data["degraded"] is True
    assert [e["chunk_id"] for e in output.data["evidences"]] == [1, 2, 3]
