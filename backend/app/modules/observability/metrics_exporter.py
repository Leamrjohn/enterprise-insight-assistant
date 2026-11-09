"""Prometheus exporter for platform state read from the database (O2a).

    python -m app.modules.observability.metrics_exporter   # serves :9108/metrics

Every scrape runs a few aggregate queries in a read-only transaction: counts
and ages only, never questions, answers, SQL or document text, and no label
with a task, user or company id (each would be its own time series).  It also
reports how old the worker and beat heartbeats are (O4), read from the shared
heartbeat volume.  Application code is unchanged; the exporter only reads.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from app.core.settings import get_settings
from prometheus_client import start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily
from prometheus_client.registry import Collector
from sqlalchemy import URL, Engine, create_engine, text

logger = logging.getLogger(__name__)

EXPORTER_PORT = 9108
INFLIGHT_STATUSES = ("queued", "running", "retrying", "awaiting_review")
# Outbox events not yet claimed by a worker: still to publish, or in the queue.
UNCLAIMED_OUTBOX_STATUSES = ("pending", "publishing", "broker_accepted")
STRANDED_AFTER = "2 minutes"
RESERVED_BILLING_STALE_AFTER = "10 minutes"
HEARTBEATS = ("worker", "beat")

QUERIES = {
    "tasks_inflight": text(
        "SELECT status, count(*) FROM analysis_tasks "
        "WHERE status = ANY(:statuses) GROUP BY status"
    ).bindparams(statuses=list(INFLIGHT_STATUSES)),
    "outbox_unclaimed": text(
        "SELECT status, count(*), "
        "coalesce(extract(epoch FROM now() - min(created_at)), 0) "
        "FROM analysis_task_outbox_events "
        "WHERE status = ANY(:statuses) GROUP BY status"
    ).bindparams(statuses=list(UNCLAIMED_OUTBOX_STATUSES)),
    "leases_expired": text(
        "SELECT count(*) FROM task_execution_attempts "
        "WHERE status = 'running' AND lease_expires_at < now()"
    ),
    "tasks_stranded": text(
        "SELECT count(*) FROM analysis_tasks WHERE status = 'retrying' "
        "AND active_execution_id IS NULL "
        f"AND updated_at < now() - interval '{STRANDED_AFTER}'"
    ),
    "billing": text(
        "SELECT billing_status, count(*) FROM model_call_records GROUP BY 1"
    ),
    "reserved_billing_stale": text(
        "SELECT count(*) FROM model_call_records WHERE billing_status = 'reserved' "
        f"AND created_at < now() - interval '{RESERVED_BILLING_STALE_AFTER}'"
    ),
}


def read_only_engine() -> Engine:
    settings = get_settings()
    url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.database_user,
        password=settings.database_password.get_secret_value(),
        host=settings.database_host,
        port=settings.database_port,
        database=settings.database_name,
    )
    # Every transaction on these connections is read-only, whatever runs on them.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args={
            "options": "-c default_transaction_read_only=on -c statement_timeout=5000",
            "application_name": "agent-metrics-exporter",
        },
    )


def heartbeat_age_seconds(directory: Path, name: str, now: float) -> float | None:
    try:
        return now - (directory / f"{name}.heartbeat").stat().st_mtime
    except FileNotFoundError:
        return None


def build_metrics(
    results: dict[str, list[tuple]],
    heartbeat_ages: dict[str, float | None],
    *,
    up: bool,
    duration: float,
) -> Iterator[GaugeMetricFamily]:
    """Turn query rows into metric families; statuses with no rows report 0."""
    yield GaugeMetricFamily(
        "agent_exporter_up", "1 when the last database read succeeded.", value=int(up)
    )
    yield GaugeMetricFamily(
        "agent_exporter_query_seconds",
        "Seconds the database reads took.",
        value=duration,
    )
    heartbeat = GaugeMetricFamily(
        "agent_heartbeat_age_seconds",
        "Seconds since the process last wrote its heartbeat (O4).",
        labels=["process"],
    )
    for name, age in heartbeat_ages.items():
        if age is not None:
            heartbeat.add_metric([name], age)
    yield heartbeat
    if not up:
        return

    inflight = GaugeMetricFamily(
        "agent_tasks_inflight", "Analysis tasks not yet finished.", labels=["status"]
    )
    counts = dict(results["tasks_inflight"])
    for status in INFLIGHT_STATUSES:
        inflight.add_metric([status], counts.get(status, 0))
    yield inflight

    outbox = GaugeMetricFamily(
        "agent_outbox_unclaimed_events",
        "Outbox events no worker has claimed yet.",
        labels=["status"],
    )
    rows = {status: (count, age) for status, count, age in results["outbox_unclaimed"]}
    for status in UNCLAIMED_OUTBOX_STATUSES:
        outbox.add_metric([status], rows.get(status, (0, 0))[0])
    yield outbox
    yield GaugeMetricFamily(
        "agent_outbox_pending_age_seconds",
        "Age of the oldest outbox event no worker has claimed (0 when none).",
        value=max((float(age) for _, age in rows.values()), default=0.0),
    )
    yield GaugeMetricFamily(
        "agent_leases_expired",
        "Running execution attempts whose lease has expired.",
        value=results["leases_expired"][0][0],
    )
    yield GaugeMetricFamily(
        "agent_tasks_stranded",
        f"Retrying tasks with no execution for over {STRANDED_AFTER}.",
        value=results["tasks_stranded"][0][0],
    )
    billing = GaugeMetricFamily(
        "agent_model_call_records",
        "Model call ledger rows by billing status.",
        labels=["billing_status"],
    )
    for status, count in results["billing"]:
        billing.add_metric([status], count)
    yield billing
    yield GaugeMetricFamily(
        "agent_reserved_billing_stale",
        f"Ledger rows still reserved after {RESERVED_BILLING_STALE_AFTER}.",
        value=results["reserved_billing_stale"][0][0],
    )


class PlatformCollector(Collector):
    def __init__(self, engine: Engine, heartbeat_dir: Path) -> None:
        self._engine = engine
        self._heartbeat_dir = heartbeat_dir

    def collect(self) -> Iterable[GaugeMetricFamily]:
        started = time.monotonic()
        results: dict[str, list[tuple]] = {}
        up = True
        try:
            with self._engine.connect() as connection:
                for name, query in QUERIES.items():
                    results[name] = [tuple(row) for row in connection.execute(query)]
        except Exception:
            logger.exception("metrics_exporter_query_failed")
            up = False
        now = time.time()
        ages = {
            name: heartbeat_age_seconds(self._heartbeat_dir, name, now)
            for name in HEARTBEATS
        }
        return list(
            build_metrics(results, ages, up=up, duration=time.monotonic() - started)
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    heartbeat_dir = Path(os.environ.get("AGENT_HEARTBEAT_DIR", "/heartbeat"))
    REGISTRY.register(PlatformCollector(read_only_engine(), heartbeat_dir))
    start_http_server(EXPORTER_PORT)
    logger.info("metrics_exporter_started", extra={"port": EXPORTER_PORT})
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
