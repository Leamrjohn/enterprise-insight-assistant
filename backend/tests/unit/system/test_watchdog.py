"""O4: a hung Celery process is restarted through its stale heartbeat."""

import os
import sys
import time

import pytest
from app.core import heartbeat, watchdog
from app.core.celery_app import celery_app


@pytest.fixture(autouse=True)
def heartbeat_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, "HEARTBEAT_DIR", tmp_path)
    return tmp_path


def _age(name, seconds):
    path = heartbeat.heartbeat_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="ascii")
    then = time.time() - seconds
    os.utime(path, (then, then))


def _reason(started_ago, **kwargs):
    now = time.time()
    return watchdog.stale_reason(
        "worker",
        started_at=now - started_ago,
        now=now,
        max_age=kwargs.get("max_age", 120),
        startup_grace=kwargs.get("startup_grace", 180),
    )


def test_fresh_heartbeat_is_healthy():
    _age("worker", 10)

    assert _reason(started_ago=600) is None


def test_old_heartbeat_is_stale():
    _age("worker", 200)

    assert "200s old" in _reason(started_ago=600)


def test_missing_heartbeat_waits_for_startup_grace():
    assert _reason(started_ago=60) is None
    assert "no heartbeat" in _reason(started_ago=300)


def test_file_left_from_a_previous_start_is_ignored_during_grace():
    _age("worker", 1000)

    assert _reason(started_ago=30) is None
    assert _reason(started_ago=400) is not None


def test_supervise_returns_the_child_exit_code(tmp_path):
    code = watchdog.supervise(
        [sys.executable, "-c", "raise SystemExit(3)"],
        "worker",
        max_age=120,
        startup_grace=180,
        sleep=lambda _: None,
    )

    assert code == 3


def test_supervise_kills_a_child_whose_heartbeat_stops():
    # The child never writes a heartbeat; with no grace the watchdog must
    # kill it instead of waiting for it to finish.
    started = time.time()
    code = watchdog.supervise(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        "worker",
        max_age=1,
        startup_grace=0,
        sleep=lambda _: time.sleep(0.05),
    )

    assert code == 1
    assert time.time() - started < 30


def test_check_mode_reports_health(capsys):
    assert watchdog.main(["--check", "worker"]) == 1
    _age("worker", 5)
    assert watchdog.main(["--check", "worker"]) == 0
    _age("worker", 500)
    assert watchdog.main(["--check", "worker"]) == 1


def test_worker_and_beat_write_heartbeats():
    assert heartbeat.WorkerHeartbeat in celery_app.steps["worker"]

    class FakeScheduler(heartbeat.HeartbeatScheduler):
        def __init__(self):
            pass

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(heartbeat.PersistentScheduler, "tick", lambda self: 1.0)
        assert FakeScheduler().tick() == 1.0
    assert heartbeat.heartbeat_age_seconds("beat") < 5
