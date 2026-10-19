import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / "scripts" / "ops" / "assert-p0-evaluation-budget.ps1"


def _write_run(path: Path, *, cost_status: str, settled_cost: str | None) -> None:
    path.write_text(
        json.dumps(
            {
                "run_id": path.stem,
                "metrics": {
                    "cost_status": cost_status,
                    "settled_cost": settled_cost,
                },
            }
        ),
        encoding="utf-8",
    )


def _run_budget_check(*paths: Path, planned_cost: str = "0") -> subprocess.CompletedProcess[str]:
    escaped_script = str(SCRIPT).replace("'", "''")
    escaped_paths = ", ".join(
        "'{}'".format(str(path).replace("'", "''")) for path in paths
    )
    command = (
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); "
        f"& '{escaped_script}' -RunPath @({escaped_paths}) "
        f"-PlannedMaxCostUsd '{planned_cost}'"
    )
    command = [
        "pwsh",
        "-NoProfile",
        "-Command",
        command,
    ]
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_p0_budget_check_sums_settled_runs_and_reserves_the_next_task(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_run(first, cost_status="passed", settled_cost="0.004263")
    _write_run(second, cost_status="passed", settled_cost="0.004233")

    result = _run_budget_check(first, second, planned_cost="0.15")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "p0-evaluation-budget-check/v1"
    assert payload["settled_cost_usd"] == 0.008496
    assert payload["projected_cost_usd"] == 0.158496
    assert payload["remaining_cost_usd"] == 0.141504


def test_p0_budget_check_rejects_unknown_cost_and_projected_overspend(
    tmp_path: Path,
) -> None:
    unknown = tmp_path / "unknown.json"
    known = tmp_path / "known.json"
    _write_run(unknown, cost_status="unknown", settled_cost=None)
    _write_run(known, cost_status="passed", settled_cost="0.20")

    unknown_result = _run_budget_check(unknown)
    over_budget_result = _run_budget_check(known, planned_cost="0.11")

    assert unknown_result.returncode != 0
    assert "unknown or unsettled cost" in unknown_result.stderr
    assert over_budget_result.returncode != 0
    assert "P0 evaluation budget exceeded" in over_budget_result.stderr
