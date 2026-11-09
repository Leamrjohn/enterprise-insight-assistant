"""E11: fail when a Markdown file links to a repository path that does not exist.

Checks every relative link ``[text](path)`` and ``[text](path#anchor)`` in the
tracked ``*.md`` files; web links, mail links and same-page anchors are not
checked.  Links inside fenced code blocks and inline code are ignored.  Files
under ``docs/history/`` are frozen records and are skipped.

    python backend/scripts/docs/check_links.py            # from the repo root
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
INLINE_CODE = re.compile(r"`[^`]*`")
EXTERNAL = ("http://", "https://", "mailto:", "#", "claude://")
SKIPPED = ("docs/history/",)


def links(text: str) -> list[tuple[int, str]]:
    found = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        line = INLINE_CODE.sub("", line)
        for pattern in (LINK, IMAGE):
            found += [(number, m.group(1)) for m in pattern.finditer(line)]
    return found


def broken_links(root: Path, files: list[str]) -> list[str]:
    problems = []
    for name in files:
        if name.startswith(SKIPPED):
            continue
        path = root / name
        for number, target in links(path.read_text(encoding="utf-8")):
            if target.startswith(EXTERNAL):
                continue
            relative = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not relative:
                continue
            resolved = path.parent / relative
            if relative.startswith("/"):
                resolved = root / relative.lstrip("/")
            if not resolved.exists():
                problems.append(f"{name}:{number}: missing link target {target}")
    return problems


def tracked_markdown(root: Path) -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return sorted(name for name in output.decode("utf-8").split("\0") if name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    files = tracked_markdown(args.root)
    problems = broken_links(args.root, files)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} broken link(s) in {len(files)} Markdown files.")
        return 1
    print(f"All relative links resolve in {len(files)} Markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
