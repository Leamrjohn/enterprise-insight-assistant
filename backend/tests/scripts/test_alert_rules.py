"""O3 (training): every alert the design asks for exists, with a runbook entry.

Fails until you add the missing rules and docs/operations/alert_runbook.md.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
RULES = ROOT / "ops/observability/alerts.yml"
RUNBOOK = ROOT / "docs/operations/alert_runbook.md"
REQUIRED = {
    "WorkerDown",
    "BeatStalled",
    "QueueBacklog",
    "TasksStranded",
    "ExporterDown",
    "UnknownCostSpike",
}


def _rules():
    groups = yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"]
    return [rule for group in groups for rule in group["rules"]]


def test_every_required_alert_exists():
    assert REQUIRED <= {rule["alert"] for rule in _rules()}


def test_every_alert_has_severity_and_a_runbook_heading():
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for rule in _rules():
        assert rule["labels"]["severity"] in {"critical", "high", "medium"}
        assert f"## {rule['annotations']['runbook']}" in runbook
