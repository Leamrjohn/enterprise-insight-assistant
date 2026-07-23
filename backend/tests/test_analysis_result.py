import pytest
from pydantic import ValidationError

from app.schemas.analysis_result import AnalysisResult


def test_analysis_result_accepts_valid_data():
    result = AnalysisResult.model_validate(
        {"answer":" 正确答案 ",
        "citations": [{"chunk_id" : 1}],
        }
    )

    assert result.answer == "正确答案"
    assert result.citations[0].chunk_id == 1


def test_analysis_result_rejects_blank_answer():
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate({"answer": "  ","citations":[{"chunk_id" : 1}]})

def test_analysis_result_rejects_empty_citations():
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate({"answer":"正常回答", "citations":[]})

def test_analysis_result_rejects_non_positive_chunk_id():
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate({"answer":"正常回答", "citations":[{"chunk_id": 0}]})


