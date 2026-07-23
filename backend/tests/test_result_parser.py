import pytest

from app.core.exceptions import StructuredOutputError
from app.core.rag.result_parser import parse_analysis_result


def test_parse_analysis_result_accepts_allowed_citations():
    result = parse_analysis_result(
        raw_output='{"answer": "正常回答", "citations": [{"chunk_id": 1}]}',
        allowed_chunk_ids={1, 2},
    )

    assert result.answer == "正常回答"
    assert result.citations[0].chunk_id == 1

def test_parse_analysis_result_rejects_non_json_output():
    with pytest.raises(StructuredOutputError, match="not valid JSON"):
        parse_analysis_result("这不是 JSON", allowed_chunk_ids={1})

def test_parse_analysis_result_rejects_schema_invalid_output():
    with pytest.raises(StructuredOutputError, match="does not match"):
        parse_analysis_result(
            '{"answer": "正常回答", "citations": []}',
            allowed_chunk_ids={1},
        )
def test_parse_analysis_result_rejects_unavailable_citation():
    with pytest.raises(StructuredOutputError, match="Invalid cited"):
        parse_analysis_result(
            '{"answer": "正常回答", "citations": [{"chunk_id": 99}]}',
            allowed_chunk_ids={1, 2},
        )
