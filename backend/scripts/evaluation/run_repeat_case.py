"""Run one smoke case many times in a row, for a controlled before/after comparison.

It reuses the smoke runner's tenant, documents and scoring, so a result here
means the same thing as in smoke.  The Worker's configuration decides the
variant; every result records the mode the Worker actually ran with.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

STOP_POLLING = {
    "completed",
    "partial",
    "failed",
    "cancelled",
    "needs_clarification",
    "awaiting_review",
}


def emit(event, **fields):
    print(json.dumps(dict(event=event, **fields), ensure_ascii=True), flush=True)


def run_container(payload):
    import secrets

    import httpx
    from app.core.security import hash_password
    from app.core.settings import get_settings
    from app.db.session import SessionLocal, set_tenant_scope
    from app.modules.evaluation.business import evaluate_case
    from app.modules.evaluation.business_schemas import EvaluationCase
    from app.modules.evaluation.observation import observation_from_persisted_task
    from app.modules.identity.models import User
    from scripts.evaluation.prepare_business_evaluation import (
        _bootstrap_tenant,
        _create_source_snapshot,
        _request_json,
        _wait_for_document,
    )
    from scripts.evaluation.run_smoke_tests import classify
    from sqlalchemy import text

    case = EvaluationCase.model_validate(payload["case"])
    mode = get_settings().review_qualification_mode
    emit("mode", value=mode)
    rid = "repeat-" + secrets.token_hex(8)
    resources, _ = _bootstrap_tenant(rid)
    password = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        user = db.get(User, resources["user_id"])
        user.username, user.password_hash = rid, hash_password(password)
        db.commit()
    resources.update(_create_source_snapshot(resources, rid))
    total_cost = 0.0
    with httpx.Client(base_url="http://api:8000/", timeout=10) as client:

        def request(method, path, expected=200, data=None):
            return _request_json(
                client, method, path, expected_status=expected, payload=data
            )

        token = request(
            "POST", "auth/login", data={"username": rid, "password": password}
        )
        client.headers["Authorization"] = "Bearer " + token["access_token"]
        del password, token
        document_ids = {}
        for source, content in payload["documents"].items():
            doc = request(
                "POST",
                "documents",
                202,
                {
                    "name": source,
                    "source": source,
                    "content": content,
                    "min_view_role": "any",
                },
            )
            document_ids[source] = doc["id"]
            _wait_for_document(client, document_id=doc["id"], timeout_seconds=180)
        for run_no in range(1, payload["repeat"] + 1):
            start, task, passed, violations, qualifications = (
                time.monotonic(),
                {},
                False,
                [],
                None,
            )
            conversation = request(
                "POST",
                "conversations",
                201,
                {
                    "title": f"{rid} {run_no}",
                    "data_source_id": resources["data_source_id"],
                },
            )
            prefix = f"conversations/{conversation['id']}"
            accepted = request(
                "POST",
                prefix + "/messages",
                202,
                {
                    "content": case.question,
                    "document_ids": [document_ids[p] for p in case.document_scope],
                },
            )
            path = prefix + f"/tasks/{accepted['task_id']}"
            while time.monotonic() - start < 180:
                task = request("GET", path)
                if task["status"] in STOP_POLLING:
                    break
                time.sleep(2)
            timed_out = task.get("status") not in STOP_POLLING
            if timed_out:
                client.post(path + "/cancel")
            elif task["status"] not in {"cancelled", "awaiting_review"}:
                with SessionLocal() as db:
                    db.execute(text("SET TRANSACTION READ ONLY"))
                    set_tenant_scope(db, resources["company_id"])
                    observation = observation_from_persisted_task(
                        db, case_id=case.case_id, task_id=task["id"]
                    )
                    score = evaluate_case(case, observation)
                    passed, violations = score.passed, score.violations
                    qualifications = observation.actual_document_qualifications
            usage = (task.get("observability") or {}).get("model_usage", {})
            cost = usage.get("cost")
            total_cost += float(cost or 0)
            emit(
                "result",
                run=run_no,
                mode=mode,
                task_id=task.get("id"),
                status=task.get("status"),
                category=classify(task.get("status"), passed, timed_out),
                qualifications_kept=None
                if qualifications is None
                else len(qualifications),
                qualifications=qualifications,
                violations=violations,
                seconds=round(time.monotonic() - start, 2),
                tokens=usage.get("tokens"),
                cost=cost,
            )
            if cost is None or timed_out:
                emit("stop", reason="unknown_cost_or_timeout")
                return
            if total_cost > payload["max_cost"]:
                emit("stop", reason="cost_cap_reached", total_cost=total_cost)
                return
    emit("done", total_cost=total_cost)


def summarize(events) -> dict:
    rows = [e for e in events if e.get("event") == "result"]
    kept = Counter(r["qualifications_kept"] for r in rows)
    return {
        "runs": len(rows),
        "categories": dict(Counter(r["category"] for r in rows)),
        "qualifications_kept": {str(k): v for k, v in sorted(kept.items(), key=str)},
        "total_cost": sum(float(r["cost"] or 0) for r in rows),
        "total_tokens": sum(int(r["tokens"] or 0) for r in rows),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument("--max-cost", type=float, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.repeat <= 50 or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,40}", args.label
    ):
        parser.error("repeat must be 1-50 and label must be short ASCII")
    root = Path(__file__).resolve().parents[3]
    if subprocess.check_output(
        ["git", "status", "--porcelain", "--", "backend"], cwd=root, text=True
    ).strip():
        raise ValueError("Commit backend changes before an experiment run")
    selection = json.loads(
        (root / "docs/design/development_case_selection.json").read_text(
            encoding="utf-8"
        )
    )
    selected = next(c for c in selection["cases"] if c["case_id"] == args.case_id)
    fixture = root / "backend/tests/fixtures/evaluation" / selected["file"]
    raw = fixture.read_bytes()
    case = next(c for c in json.loads(raw)["cases"] if c["case_id"] == args.case_id)
    corpus = root / "data/business_knowledge_base"
    payload = {
        "case": case,
        "repeat": args.repeat,
        "max_cost": args.max_cost,
        "documents": {
            source: (corpus / source).read_text(encoding="utf-8")
            for source in case.get("document_scope") or []
        },
    }
    run_id = (
        datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%dT%H%M%S-")
        + args.label
    )
    state = root / "artifacts/experiments" / (run_id + ".json")
    state.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "event": "identity",
            "git": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True
            ).strip(),
            "case_id": args.case_id,
            "fixture_sha256": hashlib.sha256(raw).hexdigest(),
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }
    ]
    print("Run ID: " + run_id, flush=True)
    process = subprocess.Popen(
        [
            "docker",
            "exec",
            "-i",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "agent-worker-1",
            "python",
            "-u",
            "-c",
            Path(__file__).read_text(encoding="utf-8"),
            "--container",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    process.stdin.write(json.dumps(payload))
    process.stdin.close()
    for line in process.stdout:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # Runtime logs may contain sensitive details; never persist them.
        if isinstance(event, dict) and "event" in event:
            events.append(event)
            state.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(event, ensure_ascii=True), flush=True)
    summary = summarize(events)
    events.append({"event": "summary", **summary})
    state.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if process.wait() == 0 and events[-2].get("event") == "done" else 1


if __name__ == "__main__":
    if "--container" in sys.argv:
        run_container(json.loads(sys.stdin.read()))
    else:
        sys.exit(main())
