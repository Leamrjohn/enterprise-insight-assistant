"""What ToolRuntime keeps of the RAG input decides which documents are eligible."""

from app.modules.runtime.schemas import RAGSearchInputSchema


def test_the_validity_window_survives_runtime_validation():
    dumped = RAGSearchInputSchema.model_validate(
        {
            "company_id": 1,
            "document_ids": [1],
            "question": "q",
            "validity_window": ["2024-01-01", "2024-12-31"],
        }
    ).model_dump()
    assert dumped["validity_window"] == ["2024-01-01", "2024-12-31"]


def test_a_missing_window_stays_missing_so_the_tool_uses_today():
    dumped = RAGSearchInputSchema.model_validate(
        {"company_id": 1, "question": "q"}
    ).model_dump()
    assert dumped["validity_window"] is None
