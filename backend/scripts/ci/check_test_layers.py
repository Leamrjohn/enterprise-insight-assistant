"""E5: every skipped or e2e/slow-marked test file has a registered run time.

    python scripts/ci/check_test_layers.py      # from backend/

A test that is skipped everywhere silently stops protecting anything.  Each
file that uses skip, skipif, pytest.skip(), or the e2e/slow markers must be
listed in tests/test_layers.json with its layer, trigger (ci, manual or
pending) and how to run it.  Listed files that no longer skip fail too, so the
registry does not rot.  "pending" entries pass but are printed every run.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REGISTRY = BACKEND / "tests" / "test_layers.json"
MARKS = {"skip", "skipif", "e2e", "slow"}
TRIGGERS = {"ci", "manual", "pending"}


def skips(source: str) -> bool:
    """pytest.mark.skip/skipif/e2e/slow or pytest.skip() in code (not in strings)."""
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Attribute)
            and node.attr in MARKS
            and ast.unparse(node.value) == "pytest.mark"
        ):
            return True
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "pytest.skip":
            return True
    return False


def skipping_files(root: Path) -> set[str]:
    found = set()
    for path in sorted((root / "tests").rglob("test_*.py")):
        if skips(path.read_text(encoding="utf-8")):
            found.add(path.relative_to(root).as_posix())
    return found


def check(root: Path, registry: dict) -> tuple[list[str], list[str]]:
    entries = {key: value for key, value in registry.items() if not key.startswith("_")}
    problems, pending = [], []
    found = skipping_files(root)
    for name in sorted(found - set(entries)):
        problems.append(f"{name}: skips tests but has no entry in {REGISTRY.name}")
    for name in sorted(set(entries) - found):
        problems.append(f"{name}: listed in {REGISTRY.name} but no longer skips")
    for name, entry in sorted(entries.items()):
        if entry.get("trigger") not in TRIGGERS or not entry.get("how"):
            problems.append(
                f"{name}: needs trigger ({'/'.join(sorted(TRIGGERS))}) and how"
            )
        elif entry["trigger"] == "pending":
            pending.append(f"{name}: {entry['how']}")
    return problems, pending


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    problems, pending = check(BACKEND, registry)
    for line in pending:
        print(f"pending: {line}")
    for line in problems:
        print(line, file=sys.stderr)
    if problems:
        return 1
    print(f"{len(skipping_files(BACKEND))} skipping test files, all registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
