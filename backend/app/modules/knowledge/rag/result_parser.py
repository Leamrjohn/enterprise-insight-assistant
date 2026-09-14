import json

from pydantic import ValidationError
from app.core.exceptions import StructuredOutputError
from app.modules.knowledge.analysis_result import AnalysisResult


def parse_analysis_result(
    raw_output: str,
    allowed_chunk_ids: set[int],
) -> AnalysisResult:
    try:
        payload = json.loads(raw_output)
        result = AnalysisResult.model_validate(payload)

    except json.JSONDecodeError as exc:
        raise StructuredOutputError("Model output is not valid JSON") from exc

    except ValidationError as exc:
        raise StructuredOutputError(
            "Model output does not match the required analysis-result schema"
        ) from exc

    cited_chunk_ids = {citation.chunk_id for citation in result.citations}
    invalid_chunk_ids = cited_chunk_ids - allowed_chunk_ids
    if invalid_chunk_ids:
        raise StructuredOutputError(
            f"Invalid cited chunk IDs: {sorted(invalid_chunk_ids)}"
        )
    return result
