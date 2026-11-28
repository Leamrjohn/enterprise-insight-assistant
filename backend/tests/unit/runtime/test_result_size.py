"""T5: fit_rows keeps the leading rows that fit a token limit."""

from app.modules.runtime.tools.result_size import fit_rows, result_tokens


def _big(rows: int) -> dict:
    return {
        "status": "ready",
        "columns": ["region", "revenue"],
        "rows": [["华东", 1000 + i] for i in range(rows)],
    }


def test_5000_rows_are_cut_to_the_leading_rows_that_fit():
    data = _big(5000)
    assert result_tokens(data) > 8_000

    fitted = fit_rows(data, 8_000)

    assert result_tokens(fitted) <= 8_000
    assert fitted["truncated"] is True
    kept = fitted["rows"]
    assert 0 < len(kept) < 5000
    assert kept == data["rows"][: len(kept)]
    # As many as fit: one more row would go over.
    assert result_tokens({**fitted, "rows": data["rows"][: len(kept) + 1]}) > 8_000
    assert fitted["columns"] == data["columns"] and fitted["status"] == "ready"


def test_the_input_is_not_changed():
    data = _big(100)
    fit_rows(data, 50)
    assert len(data["rows"]) == 100 and "truncated" not in data


def test_when_no_row_fits_rows_is_empty():
    assert fit_rows(_big(10), 1)["rows"] == []
