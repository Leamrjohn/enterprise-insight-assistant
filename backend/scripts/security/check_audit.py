"""E6: decide whether a dependency audit report blocks CI.

pip-audit reports no severity, so every Python finding blocks; npm findings block
from "high" up. A finding passes only when audit_exceptions.json lists its id (or an
alias) for that package, with a reason and an expiry date that has not passed. An
expired exception fails the check on its own, so it is renewed or removed on time.

    python scripts/security/check_audit.py pip pip-audit.json
    python scripts/security/check_audit.py npm npm-audit.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

DEFAULT_EXCEPTIONS = Path(__file__).with_name("audit_exceptions.json")
BLOCKING_NPM_SEVERITIES = {"high", "critical"}
ECOSYSTEMS = {"pip": "pypi", "npm": "npm"}
REQUIRED_FIELDS = ("ecosystem", "package", "ids", "reason", "expires")


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load_exceptions(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["exceptions"]


def _findings(kind: str, report: dict) -> list[tuple[str, str | None, str, set[str]]]:
    """(package, version, label, ids) for every finding that would block."""
    if kind == "pip":
        return [
            (dep["name"], dep["version"], vuln["id"], {vuln["id"], *vuln["aliases"]})
            for dep in report["dependencies"]
            for vuln in dep.get("vulns", [])
        ]
    findings = []
    for name, entry in report.get("vulnerabilities", {}).items():
        for via in entry["via"]:
            # A string names another vulnerable package, reported under its own entry.
            if isinstance(via, dict) and via["severity"] in BLOCKING_NPM_SEVERITIES:
                advisory = via["url"].rsplit("/", 1)[-1]
                label = f"{advisory} ({via['severity']})"
                findings.append((name, None, label, {advisory}))
    return findings


def check(kind: str, report: dict, exceptions: list[dict], today: date) -> list[str]:
    """Return one line per problem; an empty list means the audit passes."""
    ecosystem = ECOSYSTEMS[kind]
    problems = []
    active = []
    for exception in exceptions:
        missing = [field for field in REQUIRED_FIELDS if not exception.get(field)]
        if missing:
            raise ValueError(f"exception {exception!r} lacks {', '.join(missing)}")
        if exception["ecosystem"] != ecosystem:
            continue
        expires = date.fromisoformat(exception["expires"])
        if expires < today:
            problems.append(
                f"exception for {exception['package']} expired on {expires.isoformat()}"
            )
        else:
            active.append(exception)

    for package, version, label, ids in _findings(kind, report):
        covered = any(
            _normalize(exception["package"]) == _normalize(package)
            and exception.get("version", version) == version
            and ids & set(exception["ids"])
            for exception in active
        )
        if not covered:
            where = f"{package} {version}" if version else package
            problems.append(f"{where}: {label} has no exception")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=sorted(ECOSYSTEMS))
    parser.add_argument("report", type=Path)
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    args = parser.parse_args(argv)

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"refused: cannot read {args.report}: {exc}")
        return 2
    problems = check(
        args.kind, report, load_exceptions(args.exceptions), datetime.now(UTC).date()
    )
    for problem in problems:
        print(problem)
    print(f"{args.kind} audit: {'blocked' if problems else 'passed'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
