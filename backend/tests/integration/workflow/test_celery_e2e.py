import os
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.workflow.tasks import process_analysis_task
from app.db.session import SessionLocal
from app.modules.workflow.models import AnalysisTask
from app.modules.organizations.models import (
    BusinessDataSource,
    Company,
    CompanyMember,
    SchemaSnapshot,
)
from app.modules.conversations.models import Conversation
from app.modules.identity.models import User


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("RUN_REAL_CELERY_E2E") != "1",
        reason=(
            "set RUN_REAL_CELERY_E2E=1 and run "
            "docker compose --profile test up -d worker-test"
        ),
    ),
]


def _wait_for_worker(result, *, timeout_seconds: float = 45) -> None:
    deadline = time.monotonic() + timeout_seconds
    while not result.ready():
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Worker did not finish the task within {timeout_seconds} seconds"
            )
        time.sleep(0.2)

    result.get(timeout=1, propagate=True)


def test_cancelled_task_is_skipped_by_real_worker(
    migrated_test_database: None,
) -> None:
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex

        user = User(name=f"ceshi-{suffix}", api_key=f"123-{suffix}")
        db.add(user)
        db.flush()
        task = AnalysisTask(
            user_id=user.id, question="ceshinwenti", status="cancelled", stage="queued"
        )
        db.add(task)
        db.flush()
        db.commit()
        task_id = task.id
        user_id = user.id

        result = process_analysis_task.apply_async(
            kwargs={"task_id": task_id},
            queue="test",
        )
        _wait_for_worker(result)

        db.expire_all()  # 不使用本地 Session 缓存的旧对象

        record = db.get(AnalysisTask, task.id)
        assert record is not None
        assert record.status == "cancelled"
        assert record.attempt_count == 0
    finally:
        db.rollback()
        if task_id is not None:
            record_task = db.get(AnalysisTask, task_id)
            if record_task is not None:
                db.delete(record_task)
                db.flush()
        if user_id is not None:
            record_user = db.get(User, user_id)
            if record_user is not None:
                db.delete(record_user)
        db.commit()
        db.close()


def test_real_worker_persists_planner_model_attempts(
    migrated_test_database: None,
) -> None:
    db = SessionLocal()
    task_id: int | None = None
    user_id: int | None = None
    try:
        suffix = uuid4().hex
        user = User(name=f"planner-e2e-{suffix}", api_key=f"planner-key-{suffix}")
        db.add(user)
        db.flush()
        task = AnalysisTask(
            user_id=user.id,
            question="你好，请介绍一下你能做什么。",
            status="queued",
            stage="queued",
        )
        db.add(task)
        db.commit()
        task_id = task.id
        user_id = user.id

        result = process_analysis_task.apply_async(
            kwargs={"task_id": task_id},
            queue="test",
        )
        _wait_for_worker(result)

        db.expire_all()
        record = db.get(AnalysisTask, task_id)
        assert record is not None
        assert record.status == "completed"
        assert record.result_data is not None
        assert record.result_data["type"] == "langgraph_workflow"
        assert record.result_data["planner_result"]["status"] == "ready"
        assert record.result_data["planner_result"]["attempts"]["model_attempts"] in {
            1,
            2,
        }
        assert record.result_data["plan"]["action"] == "direct_response"
        assert record.result_data["terminal_result"]["outcome"] == "direct_response"
    finally:
        db.rollback()
        if task_id is not None:
            record_task = db.get(AnalysisTask, task_id)
            if record_task is not None:
                db.delete(record_task)
                db.flush()
        if user_id is not None:
            record_user = db.get(User, user_id)
            if record_user is not None:
                db.delete(record_user)
        db.commit()
        db.close()


def test_conversation_api_commits_before_real_worker_and_returns_assistant_message(
    migrated_test_database: None,
) -> None:
    db = SessionLocal()
    task_id: int | None = None
    conversation_id: int | None = None
    user_id: int | None = None
    company_id: int | None = None
    data_source_id: int | None = None
    try:
        suffix = uuid4().hex
        api_key = f"conversation-api-key-{suffix}"
        user = User(name=f"conversation-api-{suffix}", api_key=api_key)
        db.add(user)
        db.flush()
        user_id = user.id
        company = Company(name=f"conversation-e2e-company-{suffix}")
        db.add(company)
        db.flush()
        company_id = company.id
        db.add(
            CompanyMember(
                company_id=company.id,
                user_id=user.id,
                role="owner",
                status="approved",
            )
        )
        source = BusinessDataSource(
            company_id=company.id,
            name="e2e-direct-response-source",
            connection_config={
                "host": "unused-for-direct-response",
                "port": 5432,
                "database": "unused",
                "user": "readonly",
                "schema": "public",
            },
            credential_env_var="BUSINESS_DATABASE_PASSWORD",
            status="ready",
        )
        db.add(source)
        db.flush()
        data_source_id = source.id
        snapshot = SchemaSnapshot(
            data_source_id=source.id,
            fingerprint="e" * 64,
            catalog={"tables": {}},
            discovered_by_user_id=user.id,
        )
        db.add(snapshot)
        db.flush()
        source.active_schema_snapshot_id = snapshot.id
        db.commit()
        headers = {"X-API-Key": api_key}

        app.dependency_overrides.clear()
        with TestClient(app) as client:
            conversation_response = client.post(
                "/conversations",
                headers=headers,
                json={
                    "title": "Planner E2E",
                    "data_source_id": data_source_id,
                },
            )
            assert conversation_response.status_code == 201
            conversation_id = conversation_response.json()["id"]

            accepted_response = client.post(
                f"/conversations/{conversation_id}/messages",
                headers=headers,
                json={"content": "你好，请介绍一下你能做什么。"},
            )
            assert accepted_response.status_code == 202
            accepted = accepted_response.json()
            task_id = accepted["task_id"]
            assert accepted["assistant_message"]["status"] == "queued"

            deadline = time.monotonic() + 45
            assistant = accepted["assistant_message"]
            while assistant["status"] not in {
                "completed",
                "partial",
                "failed",
                "cancelled",
            }:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Assistant message did not reach a terminal status within 45 seconds"
                    )
                time.sleep(1)
                messages_response = client.get(
                    f"/conversations/{conversation_id}/messages",
                    headers=headers,
                )
                assert messages_response.status_code == 200
                assistant = messages_response.json()[-1]

        assert assistant["status"] == "completed"
        assert assistant["content"]
        assert assistant["analysis_task_id"] == task_id
        assert "result_data" not in assistant

        db.expire_all()
        task = db.get(AnalysisTask, task_id)
        assert task is not None
        assert task.result_data is not None
        assert {
            "plan",
            "planner_result",
            "data_result",
            "knowledge_result",
            "review_result",
        }.issubset(task.result_data)
    finally:
        db.rollback()
        if task_id is not None:
            task = db.get(AnalysisTask, task_id)
            if task is not None:
                db.delete(task)
                db.flush()
        if conversation_id is not None:
            conversation = db.get(Conversation, conversation_id)
            if conversation is not None:
                db.delete(conversation)
                db.flush()
        if data_source_id is not None:
            source = db.get(BusinessDataSource, data_source_id)
            if source is not None:
                db.delete(source)
                db.flush()
        if company_id is not None:
            company = db.get(Company, company_id)
            if company is not None:
                db.delete(company)
                db.flush()
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                db.delete(user)
        db.commit()
        db.close()
