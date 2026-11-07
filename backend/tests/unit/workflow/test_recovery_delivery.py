from app.modules.workflow import outbox_tasks, tasks


class _Session:
    def close(self):
        pass


def _fake_recovery(monkeypatch, *, recovered_ids, failing_ids=()):
    """Patch DB and broker; return the list of task ids the broker accepted."""
    delivered = []

    def delay(*, task_id):
        if task_id in failing_ids:
            raise ConnectionError("broker unavailable")
        delivered.append(task_id)

    monkeypatch.setattr(outbox_tasks, "SessionLocal", _Session)
    monkeypatch.setattr(
        outbox_tasks, "recover_expired_executions", lambda db: list(recovered_ids)
    )
    monkeypatch.setattr(tasks.process_analysis_task, "delay", delay)
    return delivered


def test_recovered_tasks_are_all_delivered(monkeypatch):
    delivered = _fake_recovery(monkeypatch, recovered_ids=[11, 12])

    result = outbox_tasks.recover_expired_analysis_executions()

    assert delivered == [11, 12]
    assert result == {"recovered": 2, "delivered": 2}


def test_one_failed_delivery_does_not_block_the_rest(monkeypatch):
    # Recovery already committed these as retrying, so a skipped one is never retried.
    delivered = _fake_recovery(
        monkeypatch, recovered_ids=[11, 12, 13], failing_ids={12}
    )

    result = outbox_tasks.recover_expired_analysis_executions()

    assert delivered == [11, 13]
    assert result == {"recovered": 3, "delivered": 2}


def test_reconcile_redelivers_stranded_tasks(monkeypatch):
    delivered = _fake_recovery(monkeypatch, recovered_ids=[], failing_ids={22})
    monkeypatch.setattr(
        outbox_tasks, "stranded_retrying_task_ids", lambda db, **_: [21, 22]
    )

    result = outbox_tasks.reconcile_stranded_analysis_tasks()

    assert delivered == [21]
    assert result == {"stranded": 2, "delivered": 1}
