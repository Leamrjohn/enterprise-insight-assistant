"""Configuration catalog: every setting the platform reads, by domain (K2).

    python -m app.core.config.catalog --check   # CI: .env.example matches
    python -m app.core.config.catalog --write   # regenerate .env.example

The catalog is built from the Settings domains (K1), so a new field appears in
the example file as soon as it is declared, and CI fails until the file is
regenerated.  ``unknown_keys`` finds names in the env file or the process
environment that no setting declares: a misspelt ``RAG_RERANK_TOPK`` would
otherwise be ignored and the default would apply silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from pydantic import SecretStr

from app.core.config.base import BACKEND_DIR
from app.core.config.settings import DOMAINS

EXAMPLE_FILE = BACKEND_DIR / ".env.example"

# Example values that differ from the code default: placeholders for secrets
# and the values a local setup is expected to start from.
EXAMPLE_VALUES = {
    "LOG_DIR": "./logs",
    "STORAGE_DIR": "./storage",
    "CORS_ORIGINS": '["http://localhost:5173","http://127.0.0.1:5173"]',
    "JWT_SECRET": "replace_with_a_long_random_secret",
    "DATABASE_PASSWORD": "replace_with_your_project_password",
    "BUSINESS_DATABASE_PASSWORD": "replace_with_readonly_password",
    "MODEL_PRICE_TABLE_VERSION": "deepseek-v4.1-flash-peak-2026-10-10",
    "MODEL_PRICE_TABLE": (
        '[{"price_id":"deepseek-v4.1-flash-peak-cache-miss","provider":"deepseek",'
        '"model_name":"deepseek-v4-flash","parameters":{},'
        '"prompt_per_1k":"0.0003","completion_per_1k":"0.0012"}]'
    ),
}

COMMENTS = {
    "REVIEW_QUALIFICATION_MODE": [
        (
            "证据复核标出文档限定条件的方式：sentence_ref（默认）让模型只返回句子编号；"
            "text 让模型抄写原句"
        ),
        (
            "回退：改成 text 并重启 worker。注意：按 text 录制的回放"
            "（如 run_memory_flag_evaluation）在 sentence_ref 下会找不到录音"
        ),
    ],
    "ANALYSIS_TASK_MODEL_MAX_CALLS": [
        (
            "Server-owned limits, frozen into each task at admission. "
            "Clients cannot raise them."
        ),
    ],
    "MODEL_PRICE_TABLE_VERSION": [
        "Conservative peak, cache-miss rates for the legacy deepseek-v4-flash alias.",
        "Revalidate against the provider price page before changing models or prices.",
    ],
    "DATA_SOURCE_CREDENTIAL_ENV_ALLOWLIST": [
        (
            "Credential names tenant data sources may read "
            "(JSON list; platform settings are always refused)."
        ),
        (
            "Adding a name lets every company admin use it until A11b binds "
            "credentials to companies."
        ),
    ],
}

# Data-source credentials are read by the names DATA_SOURCE_CREDENTIAL_ENV_ALLOWLIST
# lists, not by Settings fields.  The demo connections use these two.
CREDENTIAL_EXAMPLES = {
    "ACME_DEMO_DATABASE_PASSWORD": "acme_demo_readonly_password",
    "BETA_DEMO_DATABASE_PASSWORD": "beta_demo_readonly_password",
}


@dataclass(frozen=True)
class ConfigItem:
    env: str
    domain: str
    secret: bool
    example: str


def _render(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, Decimal | Path):
        return str(value)
    return str(value)


def catalog() -> list[ConfigItem]:
    items = []
    for domain in DOMAINS:
        name = domain.__name__.removesuffix("Config")
        for field_name, field in domain.model_fields.items():
            env = field_name.upper()
            annotation = str(field.annotation)
            secret = "SecretStr" in annotation
            default = field.get_default(call_default_factory=True)
            example = EXAMPLE_VALUES.get(env, _render(default))
            items.append(ConfigItem(env, name, secret, example))
    return items


def declared_names() -> set[str]:
    return {item.env for item in catalog()}


def _prefixes(names: Iterable[str]) -> set[str]:
    return {name.split("_", 1)[0] + "_" for name in names}


def unknown_keys(
    env_file_keys: Iterable[str],
    environ: Mapping[str, str],
    *,
    credential_names: Iterable[str] = (),
) -> list[str]:
    """Names no setting declares: every key of the env file, and process
    variables that share a prefix with a declared name (PATH, HOME and the
    like are not the platform's to judge)."""
    declared = declared_names() | set(credential_names)
    prefixes = tuple(_prefixes(declared))
    candidates = {key.upper() for key in env_file_keys} | {
        key.upper() for key in environ if key.upper().startswith(prefixes)
    }
    return sorted(candidates - declared)


def render_example() -> str:
    lines = [
        "# Generated by `python -m app.core.config.catalog --write` from the",
        "# settings in app/core/config/ (K2).  Edit the settings, not this file.",
    ]
    current = None
    for item in catalog():
        if item.domain != current:
            lines += ["", f"# --- {item.domain} ---"]
            current = item.domain
        lines += [f"# {line}" for line in COMMENTS.get(item.env, [])]
        lines.append(f"{item.env}={item.example}")
    lines += ["", "# --- data source credentials (names listed in the allowlist) ---"]
    lines += [f"{name}={value}" for name, value in CREDENTIAL_EXAMPLES.items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    expected = render_example()
    if args.write:
        EXAMPLE_FILE.write_text(expected, encoding="utf-8", newline="\n")
        print(f"wrote {EXAMPLE_FILE.name} ({len(catalog())} settings)")
        return 0
    actual = EXAMPLE_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    if actual != expected:
        print(
            f"{EXAMPLE_FILE.name} does not match the settings catalog; run "
            "`python -m app.core.config.catalog --write` and commit it.",
            file=sys.stderr,
        )
        return 1
    print(f"{EXAMPLE_FILE.name} matches the catalog ({len(catalog())} settings).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
