"""Production-style import smoke tests that do not inherit pytest model imports."""

from pathlib import Path
import subprocess
import sys


def test_fresh_process_configures_all_orm_mappers() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.main import app; "
                "from sqlalchemy.orm import configure_mappers; "
                "configure_mappers(); "
                "assert app.title"
            ),
        ],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
