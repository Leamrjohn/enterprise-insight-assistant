"""The validation script passes SQL values to the driver, not interpolation."""

import runpy
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("parameters", [None, ("2025-08-01", "2025-08-01")])
def test_scalar_preserves_sql_and_parameters(monkeypatch, parameters):
    directory = Path(__file__).resolve().parents[2] / "scripts" / "data"
    monkeypatch.syspath_prepend(str(directory))
    module = runpy.run_path(str(directory / "validate_business_data.py"))
    cursor = Mock()
    cursor.fetchone.return_value = (17,)
    sql = "SELECT 17" if parameters is None else "SELECT %s::date, %s::date"

    assert module["scalar"](cursor, sql, parameters) == 17
    cursor.execute.assert_called_once_with(sql, parameters)
