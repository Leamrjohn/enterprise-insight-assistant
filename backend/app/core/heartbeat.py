"""Liveness heartbeats for the Celery worker and beat (O4).

Docker restarts a container only when its main process exits; it does not act
on ``unhealthy``.  So each Celery process touches a heartbeat file from the
loop that would stop if the process hung, and ``app.core.watchdog`` (the
container's main process) exits when the file goes stale.

- worker: a bootstep on the worker's own timer, which runs on the main event
  loop of the consumer; a blocked loop stops the heartbeat.
- beat: the scheduler touches the file on every tick.

``celery inspect ping`` is not used: it misreads long tasks and Redis blips.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from celery import bootsteps
from celery.beat import PersistentScheduler

HEARTBEAT_DIR = Path(os.environ.get("AGENT_HEARTBEAT_DIR", "/tmp/agent-heartbeat"))
HEARTBEAT_INTERVAL_SECONDS = 30.0


def heartbeat_path(name: str) -> Path:
    return HEARTBEAT_DIR / f"{name}.heartbeat"


def touch(name: str) -> None:
    path = heartbeat_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{time.time():.3f}\n", encoding="ascii")


def heartbeat_age_seconds(name: str, *, now: float | None = None) -> float | None:
    """Seconds since the last heartbeat, or None when there has been none."""
    try:
        written = heartbeat_path(name).stat().st_mtime
    except FileNotFoundError:
        return None
    return (time.time() if now is None else now) - written


class WorkerHeartbeat(bootsteps.StartStopStep):
    """Touch ``worker.heartbeat`` from the worker timer (main event loop)."""

    requires = ("celery.worker.components:Timer",)

    def __init__(self, worker, **kwargs) -> None:
        super().__init__(worker, **kwargs)
        self._timer_entry = None

    def start(self, worker) -> None:
        touch("worker")
        self._timer_entry = worker.timer.call_repeatedly(
            HEARTBEAT_INTERVAL_SECONDS, touch, ("worker",)
        )

    def stop(self, worker) -> None:
        if self._timer_entry is not None:
            self._timer_entry.cancel()


class HeartbeatScheduler(PersistentScheduler):
    """Beat's default scheduler that also touches ``beat.heartbeat`` per tick."""

    def tick(self, *args, **kwargs):
        touch("beat")
        return super().tick(*args, **kwargs)
