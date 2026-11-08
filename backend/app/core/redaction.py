"""Shared sensitive-text patterns for logs and task traces."""

import re

REDACTED = "[REDACTED]"

# Keys, emails, mainland mobile numbers, named credentials and bearer tokens.
SENSITIVE_PATTERN = re.compile(
    r"\bsk-[A-Za-z0-9_-]+"
    r"|[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    r"|(?<!\d)(?:\+?86[ -]?)?1[3-9](?:[ -]?\d){9}(?!\d)"
    r"|\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*\S+"
    r"|\bBearer\s+\S+",
    re.IGNORECASE,
)


def redact_text(text: str) -> str:
    """Replace each sensitive match so the surrounding message stays readable."""
    return SENSITIVE_PATTERN.sub(REDACTED, text)
