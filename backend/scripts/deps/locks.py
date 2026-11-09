"""E2: helpers for scripts/deps/update_locks.sh.

``pins`` prints ``name==version`` for every package in one or more lock files,
so a new lock can be compiled with the versions an existing lock already
tested.  Later files win; names given with ``--except`` are left out so they
can move.

``hash`` turns pip-compile's pins (compiled without hashes) into a lock with
one line per package and the sha256 of the file pip downloaded for it on this
platform (Linux, CPython 3.12), where every image and CI job installs.
pip-compile --generate-hashes would instead download every platform's files
to hash them: several GB for torch alone.

    python scripts/deps/locks.py pins a.lock b.lock --except pillow
    python scripts/deps/locks.py hash pins.txt --downloads /tmp/x --header "..." -o x.lock
"""

from __future__ import annotations

import argparse
import re
from hashlib import sha256
from pathlib import Path

from packaging.utils import parse_sdist_filename, parse_wheel_filename
from packaging.version import Version

REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(text: str) -> dict[str, tuple[str, str, list[str]]]:
    """Map normalized name -> (name, version, hashes) for a hashed lock file."""
    entries: dict[str, tuple[str, str, list[str]]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = REQUIREMENT.match(line)
        if match:
            name, version = match.groups()
            current = normalize(name)
            entries[current] = (name, version, [])
        elif not line.startswith(" "):
            current = None
        if current is not None:
            entries[current][2].extend(HASH.findall(line))
    return entries


def pins(texts: list[str], excluded: set[str]) -> list[str]:
    merged: dict[str, str] = {}
    for text in texts:
        for key, (name, version, _) in parse_lock(text).items():
            merged[key] = f"{name}=={version}"
    return [merged[key] for key in sorted(merged) if key not in excluded]


def downloaded_hashes(downloads: Path) -> dict[tuple[str, Version], list[str]]:
    """Map (normalized name, version) -> sha256 of each file in a pip download dir."""
    found: dict[tuple[str, Version], list[str]] = {}
    for path in sorted(downloads.iterdir()):
        if path.suffix == ".whl":
            name, version, *_ = parse_wheel_filename(path.name)
        else:
            name, version = parse_sdist_filename(path.name)
        digest = sha256(path.read_bytes()).hexdigest()
        found.setdefault((normalize(name), version), []).append(digest)
    return found


def hash_pins(
    text: str, found: dict[tuple[str, Version], list[str]], header: list[str]
) -> list[str]:
    """One line per pinned package with the hashes of its downloaded files."""
    lines = [f"# {line}" if line else "#" for line in header]
    for key in sorted(entries := parse_lock(text)):
        name, version, _ = entries[key]
        hashes = found.get((key, Version(version)))
        if not hashes:
            raise ValueError(f"{name}=={version}: no downloaded file for this pin")
        lines.append(
            f"{name}=={version} " + " ".join(f"--hash=sha256:{h}" for h in hashes)
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    pins_parser = commands.add_parser("pins")
    pins_parser.add_argument("locks", nargs="+", type=Path)
    pins_parser.add_argument("--except", dest="excluded", nargs="*", default=[])
    hash_parser = commands.add_parser("hash")
    hash_parser.add_argument("pins", type=Path)
    hash_parser.add_argument("--downloads", type=Path, required=True)
    hash_parser.add_argument("--header", required=True)
    hash_parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "pins":
        texts = [p.read_text(encoding="utf-8") for p in args.locks if p.exists()]
        print("\n".join(pins(texts, {normalize(n) for n in args.excluded})))
        return 0
    text = args.pins.read_text(encoding="utf-8")
    found = downloaded_hashes(args.downloads)
    lines = hash_pins(text, found, args.header.split("\n"))
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
