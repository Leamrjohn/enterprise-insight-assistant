import json
from pathlib import Path

from app.modules.evaluation.business_schemas import EvaluationFixture


def test_development_selection_has_23_unique_cases_with_matching_sources() -> None:
    root = Path(__file__).resolve().parents[4]
    selection = json.loads(
        (root / "docs/design/development_case_selection.json").read_text(
            encoding="utf-8"
        )
    )
    entries = selection["cases"]
    assert selection["scope"] == "development_only"
    assert selection["expected_case_count"] == len(entries) == 23
    assert len({entry["case_id"] for entry in entries}) == 23
    fixture_dir = root / "backend/tests/fixtures/evaluation"
    allowed_files = {
        path.name: path.resolve()
        for path in fixture_dir.glob("business_*_development_v*.json")
    }
    source_by_kind = {
        "analysis": "persisted_task",
        "clarification": "persisted_task",
        "security_rejection": "request_rejection",
        "runtime_tool_rejection": "runtime_tool_rejection",
        "sql_validation_rejection": "sql_validation_rejection",
        "sql_timeout": "sql_timeout",
        "sql_result_limit": "sql_result_limit",
        "duplicate_delivery": "duplicate_delivery",
        "execution_fence": "execution_fence",
    }
    for entry in entries:
        # Check the development-only path before reading fixture contents.
        assert entry["file"] in allowed_files, entry["file"]
        path = allowed_files[entry["file"]]
        assert path.parent == fixture_dir.resolve()
        fixture = EvaluationFixture.model_validate_json(path.read_bytes())
        assert all(case.split == "development" for case in fixture.cases)
        matches = [case for case in fixture.cases if case.case_id == entry["case_id"]]
        assert len(matches) == 1, entry["case_id"]
        assert entry["observation_source"] == source_by_kind[matches[0].evaluation_kind]
        assert entry["purpose"].strip()
