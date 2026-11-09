"""E3: fail when an image, toolchain or frontend dependency floats.

A floating reference (``latest``, ``redis:7``, ``^1.2``, ``node-version: '22'``)
lets two builds of the same commit install different things.  This check
requires:

- every container image (Dockerfile ``FROM``, compose and workflow ``image:``,
  ``docker://`` steps, ``*_IMAGE`` variables) to carry an ``@sha256:`` digest;
- every workflow action to be pinned to a 40-character commit;
- ``python-version`` and ``node-version`` in workflows to be exact ``x.y.z``;
- every version in ``frontend/package.json`` to be an exact ``x.y.z``.

    python backend/scripts/deps/check_pins.py            # from the repo root
    python backend/scripts/deps/check_pins.py --root ..  # from backend/
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
COMMIT = re.compile(r"@[0-9a-f]{40}$")
EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
FROM = re.compile(r"^\s*FROM\s+(?:--\S+\s+)*(\S+)", re.IGNORECASE)
IMAGE = re.compile(r"^\s*(?:-\s*)?(?:image|[A-Z0-9_]*_IMAGE):\s*['\"]?([^'\"\s#]+)")
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^'\"\s#]+)")
TOOL_VERSION = re.compile(r"^\s*(python-version|node-version):\s*['\"]?([^'\"\s#]+)")


def _stage_names(lines: list[str]) -> set[str]:
    """Names given with ``FROM ... AS name``; later stages may build on them."""
    names = set()
    for line in lines:
        match = re.match(r"^\s*FROM\s+.*\s+AS\s+(\S+)", line, re.IGNORECASE)
        if match:
            names.add(match.group(1).lower())
    return names


def check_dockerfile(path: str, text: str) -> list[str]:
    lines = text.splitlines()
    stages = _stage_names(lines)
    problems = []
    for number, line in enumerate(lines, 1):
        match = FROM.match(line)
        if not match:
            continue
        image = match.group(1)
        if image.lower() in stages or image.lower() == "scratch":
            continue
        if not DIGEST.search(image):
            problems.append(f"{path}:{number}: image without digest: {image}")
    return problems


def check_yaml(path: str, text: str) -> list[str]:
    problems = []
    for number, line in enumerate(text.splitlines(), 1):
        where = f"{path}:{number}"
        if match := IMAGE.match(line):
            image = match.group(1)
            if "${" not in image and not DIGEST.search(image):
                problems.append(f"{where}: image without digest: {image}")
        elif match := USES.match(line):
            target = match.group(1)
            if target.startswith("docker://"):
                if not DIGEST.search(target):
                    problems.append(f"{where}: image without digest: {target}")
            elif not target.startswith("./") and not COMMIT.search(target):
                problems.append(f"{where}: action not pinned to a commit: {target}")
        elif match := TOOL_VERSION.match(line):
            tool, version = match.groups()
            if not EXACT_VERSION.match(version):
                problems.append(f"{where}: {tool} is not exact: {version}")
    return problems


def check_package_json(path: str, text: str) -> list[str]:
    manifest = json.loads(text)
    problems = []
    for section in ("dependencies", "devDependencies"):
        for name, version in manifest.get(section, {}).items():
            if not EXACT_VERSION.match(version):
                problems.append(f"{path}: {section}.{name} is not exact: {version}")
    return problems


def find_problems(root: Path) -> list[str]:
    problems: list[str] = []
    dockerfiles = [*root.glob("**/Dockerfile"), *root.glob("**/*.Dockerfile")]
    yamls = [
        *root.glob("docker-compose*.yml"),
        *root.glob(".github/workflows/*.yml"),
    ]
    for path in sorted(dockerfiles):
        if "node_modules" not in path.parts:
            text = path.read_text(encoding="utf-8")
            problems += check_dockerfile(path.relative_to(root).as_posix(), text)
    for path in sorted(yamls):
        problems += check_yaml(
            path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")
        )
    package = root / "frontend/package.json"
    if package.exists():
        text = package.read_text(encoding="utf-8")
        problems += check_package_json("frontend/package.json", text)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    problems = find_problems(args.root)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} floating reference(s); pin them (E3).")
        return 1
    print("No floating images, actions, toolchains or frontend versions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
