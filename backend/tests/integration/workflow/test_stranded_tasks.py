from datetime import timedelta
from uuid import uuid4

from app.db.clock import database_now
from app.modules.workflow.lifecycle.execution import stranded_retrying_task_ids
from app.modules.workflow.models import AnalysisTask


def test_only_unheld_old_retrying_tasks_are_stranded(db_session, test_user):
    def task(status, stage, active_execution_id=None):
        row = AnalysisTask(
            user_id=test_user.id,
            question="销售额",
            status=status,
            stage=stage,
            active_execution_id=active_execution_id,
        )
        db_session.add(row)
        db_session.flush()
        return row.id

    lost = task("retrying", "retrying")
    running = task("running", "planning", active_execution_id=str(uuid4()))
    queued = task("queued", "queued")
    ours = {lost, running, queued}
    now = database_now(db_session)

    def stranded(at):
        found = stranded_retrying_task_ids(
            db_session, older_than=timedelta(minutes=2), now=at, limit=10_000
        )
        return set(found) & ours

    three_minutes_later = stranded(now + timedelta(minutes=3))
    right_away = stranded(now)

    assert three_minutes_later == {lost}
    assert right_away == set()
