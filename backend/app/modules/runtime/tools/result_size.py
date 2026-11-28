"""T5: how big a tool result is, in the tokens a model would read."""

import json
from typing import Any

from app.core.tokenizer import get_encoding


def result_tokens(data: Any) -> int:
    # default=str: driver rows carry Decimal and date values.
    text = json.dumps(data, ensure_ascii=False, default=str)
    return len(get_encoding().encode(text))


def fit_rows(data: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    """Keep the longest leading run of data["rows"] whose result fits max_tokens.

    Returns a new dict (data itself is not changed) with the kept rows and
    "truncated": True.  Other keys stay as they are.  When not even one row
    fits, rows is [].
    """
    rows = data["rows"]

    def fitted(count: int) -> dict[str, Any]:
        return {**data, "rows": rows[:count], "truncated": True}

    # Binary search for the largest count that fits: ~13 counts for 5000 rows.
    low, high = 0, len(rows)
    while low < high:
        middle = (low + high + 1) // 2
        if result_tokens(fitted(middle)) <= max_tokens:
            low = middle
        else:
            high = middle - 1
    return fitted(low)
