from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = PROJECT_ROOT / "scripts" / "ops" / "measure-agent-capacity.ps1"


def test_capacity_measurement_script_has_worker_guard_and_terminal_sampling() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "Worker container is not running" in source
    assert "WaitForWorkerSeconds" in source
    assert "try {" in source
    assert "$inspectExitCode" in source
    assert "TaskIds must contain positive integer IDs" in source
    assert "Start-Sleep -Milliseconds 200" in source
    assert "docker stats --no-stream" in source
    assert "Timed out before every requested task reached a terminal state" in source
    assert "agent-capacity-measurement/v1" in source
