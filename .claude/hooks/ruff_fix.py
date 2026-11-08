"""PostToolUse: run the project's pinned ruff on a backend .py file after an edit.

Formats the file and applies safe lint fixes, using backend/pyproject.toml.
Lint errors ruff cannot fix are handed back to the model as context; the hook
never blocks.
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
BACKEND = PROJECT / "backend"
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"


def main() -> int:
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    data = payload.get("tool_input") or {}
    raw = data.get("file_path") or (payload.get("tool_response") or {}).get("filePath")
    if not raw:
        return 0
    path = Path(raw).resolve()
    if path.suffix != ".py" or BACKEND not in path.parents or not path.exists():
        return 0
    if not PYTHON.exists():
        return 0

    def ruff(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(PYTHON), "-m", "ruff", *args, str(path)],
            cwd=BACKEND,
            capture_output=True,
            timeout=30,
        )

    # Fix first, then format: removing an unused import can leave blank lines.
    ruff("check", "--fix", "--quiet")
    ruff("format", "--quiet")
    result = ruff("check", "--quiet", "--output-format", "concise")
    if result.returncode != 0:
        remaining = result.stdout.decode("utf-8", "replace").strip()[:2000]
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": f"ruff check 仍有问题，需要手动修：\n{remaining}",
                    }
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
