"""E5: line coverage of a test suite must not drop below its baseline.

    python scripts/ci/check_coverage.py unit test-results/coverage.json

The baseline (tests/coverage_baseline.json) is the measured coverage, not a
target: the gate only stops coverage from falling, so nobody writes empty
tests to hit a number.  A drop of more than TOLERANCE points fails; raising a
baseline is a normal change, lowering one needs the user's approval (like any
expected value).  A suite with no baseline yet prints its value and passes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASELINE = Path(__file__).resolve().parents[2] / "tests" / "coverage_baseline.json"
TOLERANCE = 0.5  # percentage points; line counts shift slightly with code moves


def check(suite: str, measured: float, baseline: dict) -> tuple[bool, str]:
    expected = baseline.get(suite)
    if expected is None:
        return True, f"{suite}: {measured:.2f}% (no baseline yet; record it)"
    if measured + TOLERANCE < expected:
        return False, f"{suite}: {measured:.2f}% is below the baseline {expected:.2f}%"
    return True, f"{suite}: {measured:.2f}% (baseline {expected:.2f}%)"


def main(argv: list[str]) -> int:
    suite, report = argv
    measured = json.loads(Path(report).read_text(encoding="utf-8"))["totals"][
        "percent_covered"
    ]
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    ok, message = check(suite, measured, baseline)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
