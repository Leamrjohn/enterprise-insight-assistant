"""E5: coverage may rise freely but not fall below the recorded baseline."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/ci"))

from check_coverage import TOLERANCE, check, main


def test_drop_beyond_tolerance_fails():
    ok, message = check("unit", 70.0 - TOLERANCE - 0.01, {"unit": 70.0})

    assert not ok
    assert "below the baseline 70.00%" in message


def test_small_noise_and_rises_pass():
    assert check("unit", 70.0 - TOLERANCE, {"unit": 70.0})[0]
    assert check("unit", 75.0, {"unit": 70.0})[0]


def test_suite_without_baseline_passes_and_reports():
    ok, message = check("integration", 55.5, {"unit": 70.0})

    assert ok
    assert "no baseline yet" in message


def test_main_reads_the_coverage_report(tmp_path, capsys):
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"totals": {"percent_covered": 12.5}}), "utf-8")

    assert main(["no-such-suite", str(report)]) == 0
    assert "12.50%" in capsys.readouterr().out
