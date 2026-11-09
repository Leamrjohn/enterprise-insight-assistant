"""E5: a skipped test without a registered run time fails CI."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/ci"))

from check_test_layers import BACKEND, REGISTRY, check


def _tree(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_unregistered_skip_fails(tmp_path):
    root = _tree(
        tmp_path,
        {
            "tests/unit/test_a.py": "@pytest.mark.skip(reason='later')\ndef test_a(): ...\n"
        },
    )

    problems, _ = check(root, {})

    assert problems == [
        "tests/unit/test_a.py: skips tests but has no entry in test_layers.json"
    ]


def test_stale_entry_and_missing_trigger_fail(tmp_path):
    root = _tree(
        tmp_path,
        {"tests/unit/test_b.py": "pytestmark = pytest.mark.e2e\n"},
    )
    registry = {
        "tests/unit/test_b.py": {"layer": "e2e", "how": "x"},
        "tests/unit/test_gone.py": {"trigger": "manual", "how": "x"},
    }

    problems, _ = check(root, registry)

    assert any("test_b.py: needs trigger" in p for p in problems)
    assert any("test_gone.py: listed" in p for p in problems)


def test_pending_entries_pass_but_are_reported(tmp_path):
    root = _tree(tmp_path, {"tests/unit/test_c.py": "pytest.skip('x')\n"})
    registry = {"tests/unit/test_c.py": {"trigger": "pending", "how": "decide"}}

    problems, pending = check(root, registry)

    assert problems == []
    assert pending == ["tests/unit/test_c.py: decide"]


def test_repository_registry_is_complete():
    problems, _ = check(BACKEND, json.loads(REGISTRY.read_text(encoding="utf-8")))

    assert problems == []
