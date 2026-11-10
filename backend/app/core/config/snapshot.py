"""K4: a task's business configuration, frozen when the task is created.

The context, memory, rag, flags and tool domains are written to
``analysis_tasks.config_snapshot`` (no secrets live in them) with a sha256 of
the canonical JSON.  While the worker runs a task, ``runtime_settings()``
returns the settings with that snapshot applied, so changing the environment
mid-run, or recovering the task later, does not change what it uses.
Infrastructure settings (database, Redis, keys) still come from
``get_settings()``.  Tasks created before K4 have no snapshot and keep reading
the current settings.
"""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from app.core.config.context import ContextConfig
from app.core.config.flags import FeatureFlags
from app.core.config.memory import MemoryConfig
from app.core.config.rag import RagConfig
from app.core.config.settings import Settings, get_settings
from app.core.config.tool import ToolConfig

SNAPSHOT_VERSION = 1
SNAPSHOT_DOMAINS = (ContextConfig, MemoryConfig, RagConfig, FeatureFlags, ToolConfig)
SNAPSHOT_FIELDS = frozenset(
    name for domain in SNAPSHOT_DOMAINS for name in domain.model_fields
)

_task_settings: ContextVar[Settings | None] = ContextVar(
    "task_config_settings", default=None
)


def build_config_snapshot(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    return {
        "version": SNAPSHOT_VERSION,
        "values": settings.model_dump(mode="json", include=set(SNAPSHOT_FIELDS)),
    }


def config_snapshot_hash(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def settings_from_snapshot(snapshot: dict[str, Any] | None) -> Settings:
    """Current settings with the snapshot's business values applied."""
    settings = get_settings()
    if not snapshot:
        return settings
    if snapshot.get("version") != SNAPSHOT_VERSION:
        raise ValueError(
            f"Unsupported config snapshot version: {snapshot.get('version')}"
        )
    stored = snapshot.get("values") or {}
    update: dict[str, Any] = {}
    for domain in SNAPSHOT_DOMAINS:
        # Start from the current values so a field added after the task was
        # created keeps today's value; validating turns JSON into typed values.
        current = settings.domain(domain).model_dump()
        current.update({k: v for k, v in stored.items() if k in domain.model_fields})
        update.update(domain.model_validate(current).model_dump())
    return settings.model_copy(update=update)


@contextmanager
def task_config_scope(snapshot: dict[str, Any] | None) -> Iterator[Settings]:
    token = _task_settings.set(settings_from_snapshot(snapshot))
    try:
        yield _task_settings.get() or get_settings()
    finally:
        _task_settings.reset(token)


def runtime_settings() -> Settings:
    """Business settings for the running task; ``get_settings()`` outside one."""
    return _task_settings.get() or get_settings()
