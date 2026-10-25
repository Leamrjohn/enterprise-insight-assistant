"""Production-style import smoke tests that do not inherit pytest model imports."""

import subprocess
import sys
from pathlib import Path

from app.main import app


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


def test_product_router_excludes_training_crud() -> None:
    paths = set(app.openapi()["paths"])

    assert not any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in ("/todo-items", "/labels", "/prompt-templates")
        for path in paths
    )
