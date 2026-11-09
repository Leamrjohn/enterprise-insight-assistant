"""Run a Celery process and exit when its heartbeat goes stale (O4).

    python -m app.core.watchdog --heartbeat worker -- celery -A ... worker
    python -m app.core.watchdog --check worker      # Docker healthcheck

As the container's main process it starts the command as a child, forwards
stop signals to it, and checks the heartbeat file every few seconds.  When the
heartbeat is older than ``--max-age`` (or never appears within
``--startup-grace``), it kills the child and exits 1; ``restart:`` in compose
then starts a fresh container, and the execution lease of any task the hung
process held expires and is recovered as usual.
"""

from __future__ import annotations

import argparse
import logging
import signal
import subprocess
import sys
import time
from collections.abc import Callable

from app.core.heartbeat import heartbeat_age_seconds, heartbeat_path

logger = logging.getLogger("app.watchdog")

DEFAULT_MAX_AGE_SECONDS = 120.0
DEFAULT_STARTUP_GRACE_SECONDS = 180.0
CHECK_INTERVAL_SECONDS = 5.0
KILL_TIMEOUT_SECONDS = 10.0


def stale_reason(
    name: str,
    *,
    started_at: float,
    now: float,
    max_age: float,
    startup_grace: float,
) -> str | None:
    """Why the heartbeat counts as stale, or None while it is fresh."""
    age = heartbeat_age_seconds(name, now=now)
    if age is None:
        if now - started_at > startup_grace:
            return f"no heartbeat {startup_grace:.0f}s after start"
        return None
    if now - started_at <= startup_grace and age > now - started_at:
        return None  # a file left from before this start; wait for a fresh one
    if age > max_age:
        return f"heartbeat {age:.0f}s old (limit {max_age:.0f}s)"
    return None


def _stop(child: subprocess.Popen, sig: int = signal.SIGTERM) -> None:
    if child.poll() is not None:
        return
    child.send_signal(sig)
    try:
        child.wait(KILL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def supervise(
    command: list[str],
    name: str,
    *,
    max_age: float,
    startup_grace: float,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    started_at = clock()
    child = subprocess.Popen(command)
    stopping = False

    def forward(signum, _frame) -> None:
        nonlocal stopping
        stopping = True
        _stop(child, signum)

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    while True:
        code = child.poll()
        if code is not None:
            return code
        if not stopping:
            reason = stale_reason(
                name,
                started_at=started_at,
                now=clock(),
                max_age=max_age,
                startup_grace=startup_grace,
            )
            if reason is not None:
                logger.error(
                    "watchdog_restart",
                    extra={"heartbeat": name, "reason": reason, "child_pid": child.pid},
                )
                print(f"watchdog: {name} {reason}; restarting", file=sys.stderr)
                child.kill()
                child.wait()
                return 1
        sleep(CHECK_INTERVAL_SECONDS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", help="supervise: heartbeat name")
    parser.add_argument("--check", help="healthcheck: heartbeat name")
    parser.add_argument("--max-age", type=float, default=DEFAULT_MAX_AGE_SECONDS)
    parser.add_argument(
        "--startup-grace", type=float, default=DEFAULT_STARTUP_GRACE_SECONDS
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.check:
        age = heartbeat_age_seconds(args.check)
        if age is None or age > args.max_age:
            print(f"{heartbeat_path(args.check)}: stale or missing", file=sys.stderr)
            return 1
        return 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not args.heartbeat or not command:
        parser.error("--heartbeat NAME -- COMMAND ... is required")
    logging.basicConfig(level=logging.INFO)
    return supervise(
        command,
        args.heartbeat,
        max_age=args.max_age,
        startup_grace=args.startup_grace,
    )


if __name__ == "__main__":
    raise SystemExit(main())
