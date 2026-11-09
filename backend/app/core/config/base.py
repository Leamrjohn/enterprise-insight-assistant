"""Shared pieces of the configuration domains (K1).

Every domain is a plain pydantic model holding its fields and the validators
that only need those fields.  ``Settings`` inherits all domains, so the
environment variable names and ``settings.<field>`` access stay unchanged;
``settings.domain(RagConfig)`` returns one domain on its own.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[3]


class ConfigDomain(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


def require_positive(value: int) -> int:
    if value <= 0:
        raise ValueError("Value must be a positive integer")
    return value


def require_non_negative(value: int) -> int:
    if value < 0:
        raise ValueError("Value must be a non-negative integer")
    return value


def require_score(value: float) -> float:
    if not 0 <= value <= 1:
        raise ValueError("Score must be between 0 and 1")
    return value
