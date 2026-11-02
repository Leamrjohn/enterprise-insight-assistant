"""Game-day helper: submit or cancel one analysis task through the real API.

Runs inside the API container (the Worker container may be killed during a
drill).  Each submission bootstraps a disposable tenant exactly like the smoke
runner; credentials stay in process memory and are never printed.

    python -m scripts.evaluation.drill_client submit --run-id drill-1
    python -m scripts.evaluation.drill_client submit --run-id drill-8 --cancel-when-running
"""

from __future__ import annotations

import argparse
import json
import secrets

DRILL_QUESTION = "华东区2025年8月已交付订单销售额是多少？"


def _client_for_new_tenant(run_id: str):
    import httpx
    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.modules.identity.models import User
    from scripts.evaluation.prepare_business_evaluation import (
        _bootstrap_tenant,
        _create_source_snapshot,
        _request_json,
    )

    resources, _ = _bootstrap_tenant(run_id)
    password = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        user = db.get(User, resources["user_id"])
        user.username, user.password_hash = run_id, hash_password(password)
        db.commit()
    resources.update(_create_source_snapshot(resources, run_id))
    client = httpx.Client(base_url="http://localhost:8000/", timeout=30)
    token = _request_json(
        client,
        "POST",
        "auth/login",
        expected_status=200,
        payload={"username": run_id, "password": password},
    )
    client.headers["Authorization"] = "Bearer " + token["access_token"]
    del password, token
    return client, resources, _request_json


def submit(run_id: str, question: str, *, cancel_when_running: bool = False) -> dict:
    import time

    client, resources, request = _client_for_new_tenant(run_id)
    cancelled = None
    try:
        conversation = request(
            client,
            "POST",
            "conversations",
            expected_status=201,
            payload={"title": run_id, "data_source_id": resources["data_source_id"]},
        )
        accepted = request(
            client,
            "POST",
            f"conversations/{conversation['id']}/messages",
            expected_status=202,
            payload={"content": question, "document_ids": []},
        )
        prefix = f"conversations/{conversation['id']}/tasks/{accepted['task_id']}"
        if cancel_when_running:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if (
                    request(client, "GET", prefix, expected_status=200)["status"]
                    == "running"
                ):
                    break
                time.sleep(0.2)
            cancelled = request(
                client, "POST", prefix + "/cancel", expected_status=200
            )["status"]
    finally:
        client.close()
    return {
        "cancel_response_status": cancelled,
        "run_id": run_id,
        "conversation_id": conversation["id"],
        "task_id": accepted["task_id"],
        "company_id": resources["company_id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("submit",))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--question", default=DRILL_QUESTION)
    parser.add_argument("--cancel-when-running", action="store_true")
    args = parser.parse_args()
    result = submit(
        args.run_id, args.question, cancel_when_running=args.cancel_when_running
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
