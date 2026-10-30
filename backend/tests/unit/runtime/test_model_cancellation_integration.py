"""Verify cancellation visibility across real PostgreSQL sessions, without a model."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.db.session import SessionLocal
from app.modules.identity.models import User
from app.modules.runtime.model_governance import (
    ModelCallCancelled,
    model_call_scope,
    reserve_local_resource_call,
    reserve_model_call,
)
from app.modules.workflow.audit.model_call import ModelCallRecord
from app.modules.workflow.models import AnalysisTask
from app.modules.workflow.repository import cancel_task


@pytest.mark.parametrize("local_resource", [False, True])
def test_committed_cancellation_refreshes_stale_worker_session(local_resource):
    with SessionLocal() as worker:
        assert worker.bind.url.database == "agent_platform_test"
        user = User(name=f"cancel-probe-{uuid4().hex}", api_key=uuid4().hex)
        worker.add(user)
        worker.flush()
        task = AnalysisTask(
            user_id=user.id,
            question="offline cancellation probe",
            status="running",
            stage="retrieving_knowledge",
        )
        worker.add(task)
        worker.commit()
        task_id, user_id = task.id, user.id
        try:
            assert task.status == "running"
            with SessionLocal() as caller:
                cancelled = caller.get(AnalysisTask, task_id)
                cancel_task(caller, cancelled)
                caller.commit()
            # The long-running worker still holds its old identity-map object.
            assert task.status == "running"
            with (
                model_call_scope(
                    worker,
                    task=task,
                    attempt=SimpleNamespace(id=None),
                    node_name="knowledge",
                ),
                pytest.raises(ModelCallCancelled),
            ):
                if local_resource:
                    reserve_local_resource_call(
                        resource_kind="rerank",
                        model_name="offline-probe",
                        resource_usage={},
                    )
                else:
                    reserve_model_call(provider="local", model_name="offline-probe")
            assert task.status == "cancelled"
            assert worker.query(ModelCallRecord).filter_by(task_id=task_id).count() == 0
        finally:
            worker.rollback()
            worker.query(ModelCallRecord).filter_by(task_id=task_id).delete()
            worker.query(AnalysisTask).filter_by(id=task_id).delete()
            worker.query(User).filter_by(id=user_id).delete()
            worker.commit()
