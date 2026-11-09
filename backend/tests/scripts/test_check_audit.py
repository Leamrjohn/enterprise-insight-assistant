"""E6: dependency audit findings block CI unless a dated exception covers them."""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/security"))

from check_audit import DEFAULT_EXCEPTIONS, check, load_exceptions, main

TODAY = date(2026, 11, 9)


def _pip(*vulns, name="pillow", version="12.3.0"):
    return {
        "dependencies": [
            {"name": "requests", "version": "2.32.0", "vulns": []},
            {"name": name, "version": version, "vulns": list(vulns)},
        ]
    }


def _vuln(vid="PYSEC-1", aliases=("GHSA-aaaa-bbbb-cccc",)):
    return {"id": vid, "aliases": list(aliases), "fix_versions": ["13.0.0"]}


def _npm(severity="high", url="https://github.com/advisories/GHSA-2v37-7h3g-55p8"):
    return {
        "vulnerabilities": {
            "nanoid": {
                "severity": severity,
                "via": [{"source": 1, "severity": severity, "url": url}],
            },
            "vitest": {"severity": severity, "via": ["nanoid"]},
        }
    }


def _exception(ecosystem="pypi", package="Pillow", ids=("PYSEC-1",), **overrides):
    entry = {
        "ecosystem": ecosystem,
        "package": package,
        "ids": list(ids),
        "reason": "upgrade in E2",
        "expires": "2026-12-08",
    }
    if ecosystem == "pypi":
        entry["version"] = "12.3.0"
    return {**entry, **overrides}


def test_a_python_vulnerability_without_exception_blocks():
    problems = check("pip", _pip(_vuln()), [], TODAY)

    assert problems == ["pillow 12.3.0: PYSEC-1 has no exception"]


def test_a_dated_exception_covers_a_python_vulnerability():
    assert check("pip", _pip(_vuln()), [_exception()], TODAY) == []


def test_an_exception_may_name_an_alias():
    exception = _exception(ids=["GHSA-aaaa-bbbb-cccc"])

    assert check("pip", _pip(_vuln()), [exception], TODAY) == []


def test_an_exception_for_another_version_does_not_cover():
    problems = check("pip", _pip(_vuln(), version="12.4.0"), [_exception()], TODAY)

    assert problems == ["pillow 12.4.0: PYSEC-1 has no exception"]


def test_a_new_vulnerability_in_an_excepted_package_still_blocks():
    report = _pip(_vuln(), _vuln("PYSEC-2", aliases=()))

    problems = check("pip", report, [_exception()], TODAY)

    assert problems == ["pillow 12.3.0: PYSEC-2 has no exception"]


def test_an_expired_exception_blocks_even_when_it_matches():
    exception = _exception(expires="2026-11-08")

    problems = check("pip", _pip(_vuln()), [exception], TODAY)

    assert "exception for Pillow expired on 2026-11-08" in problems
    assert "pillow 12.3.0: PYSEC-1 has no exception" in problems


def test_an_exception_without_reason_or_expiry_is_refused():
    exception = _exception()
    del exception["reason"]

    with pytest.raises(ValueError, match="reason"):
        check("pip", _pip(), [exception], TODAY)


def test_npm_moderate_findings_do_not_block():
    assert check("npm", _npm("moderate"), [], TODAY) == []


def test_npm_high_findings_block_without_exception():
    problems = check("npm", _npm(), [], TODAY)

    assert problems == ["nanoid: GHSA-2v37-7h3g-55p8 (high) has no exception"]


def test_npm_high_findings_with_exception_pass():
    exception = _exception("npm", "nanoid", ["GHSA-2v37-7h3g-55p8"])

    assert check("npm", _npm(), [exception], TODAY) == []


def test_main_exits_1_on_blocking_findings(tmp_path, capsys):
    report = tmp_path / "audit.json"
    report.write_text(json.dumps(_pip(_vuln())), encoding="utf-8")
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_text(json.dumps({"exceptions": []}), encoding="utf-8")

    code = main(["pip", str(report), "--exceptions", str(exceptions)])

    assert code == 1
    assert "PYSEC-1" in capsys.readouterr().out


def test_main_exits_2_on_an_unreadable_report(tmp_path):
    report = tmp_path / "audit.json"
    report.write_text("", encoding="utf-8")

    assert main(["pip", str(report)]) == 2


def test_the_checked_in_exceptions_are_well_formed_and_dated():
    exceptions = load_exceptions(DEFAULT_EXCEPTIONS)

    assert exceptions
    assert all(date.fromisoformat(e["expires"]) for e in exceptions)
