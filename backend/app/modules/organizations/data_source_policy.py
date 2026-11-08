"""Stop tenant data sources from borrowing platform secrets or reaching platform services.

Checked when a source is created and again right before every connection, so rows
saved before this rule existed are covered too. Name matching cannot catch DNS
aliases or container IPs; network isolation is the long-term fix.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from app.core.settings import Settings, get_settings


class DataSourcePolicyError(ValueError):
    """A data source points at something the platform must keep for itself."""


def platform_setting_names() -> frozenset[str]:
    return frozenset(name.upper() for name in Settings.model_fields)


def credential_rejection(
    name: str, *, allowlist: Iterable[str], platform_names: frozenset[str]
) -> str | None:
    """Return why this credential name is refused, or None when it may be read."""
    normalized = name.upper()
    if normalized not in {item.upper() for item in allowlist}:
        return "credential is not on the data source allowlist"
    # Only company admins configure sources, so a platform secret stays refused even
    # when someone lists it by mistake; platform-owned credentials belong to A11b.
    if normalized in platform_names:
        return "credential is a platform setting"
    return None


def host_rejection(host: str, *, blocked_hosts: Iterable[str]) -> str | None:
    normalized = host.strip().rstrip(".").lower()
    if normalized in {item.lower() for item in blocked_hosts}:
        return "host is a platform service"
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return None
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        return "host is a local or metadata address"
    return None


def ensure_data_source_allowed(*, credential_env_var: str, host: str) -> None:
    settings = get_settings()
    reason = credential_rejection(
        credential_env_var,
        allowlist=settings.data_source_credential_env_allowlist,
        platform_names=platform_setting_names(),
    ) or host_rejection(host, blocked_hosts=settings.data_source_blocked_hosts)
    if reason is not None:
        raise DataSourcePolicyError(f"data source is not allowed: {reason}")
