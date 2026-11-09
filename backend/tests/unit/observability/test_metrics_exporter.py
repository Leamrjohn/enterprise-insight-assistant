"""O2a: exporter metrics are counts and ages only, with no per-tenant labels."""

import os
import time

import pytest
from app.modules.observability.metrics_exporter import (
    build_metrics,
    heartbeat_age_seconds,
)

RESULTS = {
    "tasks_inflight": [("running", 2), ("retrying", 1)],
    "outbox_unclaimed": [("pending", 3, 42.5), ("broker_accepted", 1, 7.0)],
    "leases_expired": [(1,)],
    "tasks_stranded": [(0,)],
    "billing": [("settled", 10), ("unknown", 2)],
    "reserved_billing_stale": [(0,)],
}


def _samples(families):
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in families
        for sample in family.samples
    }


def test_metrics_report_every_status_and_the_oldest_event():
    samples = _samples(
        build_metrics(RESULTS, {"worker": 12.0, "beat": None}, up=True, duration=0.1)
    )

    assert samples[("agent_tasks_inflight", (("status", "queued"),))] == 0
    assert samples[("agent_tasks_inflight", (("status", "running"),))] == 2
    assert samples[("agent_outbox_unclaimed_events", (("status", "publishing"),))] == 0
    assert samples[("agent_outbox_pending_age_seconds", ())] == 42.5
    assert samples[("agent_leases_expired", ())] == 1
    assert samples[("agent_model_call_records", (("billing_status", "unknown"),))] == 2
    assert samples[("agent_heartbeat_age_seconds", (("process", "worker"),))] == 12.0
    # A missing heartbeat is absent, so an alert can use absent() on it.
    assert ("agent_heartbeat_age_seconds", (("process", "beat"),)) not in samples


def test_failed_database_read_reports_down_and_no_stale_numbers():
    samples = _samples(build_metrics({}, {"worker": 3.0}, up=False, duration=5.0))

    assert samples[("agent_exporter_up", ())] == 0
    assert not any(name == "agent_tasks_inflight" for name, _ in samples)


def test_no_label_identifies_a_task_user_or_company():
    labels = {
        key
        for _, sample_labels in _samples(
            build_metrics(RESULTS, {"worker": 1.0, "beat": 2.0}, up=True, duration=0)
        )
        for key, _ in sample_labels
    }

    assert labels <= {"status", "billing_status", "process"}


def test_heartbeat_age_reads_the_file_time(tmp_path):
    path = tmp_path / "worker.heartbeat"
    path.write_text("x", encoding="ascii")
    then = time.time() - 30
    os.utime(path, (then, then))

    assert heartbeat_age_seconds(tmp_path, "worker", time.time()) == pytest.approx(
        30, abs=2
    )
    assert heartbeat_age_seconds(tmp_path, "beat", time.time()) is None
