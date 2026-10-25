"""Framework declarations must not disable ordinary default-value checks."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("source", "expected_codes"),
    [
        (
            (
                "from fastapi import Depends, File\n"
                "def endpoint(db=Depends(), upload=File()): pass\n"
            ),
            set(),
        ),
        ("def build(): return []\ndef endpoint(value=build()): pass\n", {"B008"}),
        ("def Depends(): return []\ndef endpoint(value=Depends()): pass\n", {"B008"}),
        ("def endpoint(value=[]): pass\n", {"B006"}),
    ],
)
def test_framework_default_exceptions_are_narrow(source, expected_codes):
    backend_dir = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--output-format=json",
            "--stdin-filename=lint_contract.py",
            "-",
        ],
        cwd=backend_dir,
        input=source,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr
    codes = {item["code"] for item in json.loads(result.stdout)}
    assert codes & {"B006", "B008"} == expected_codes
