"""Run from repository root: python backend/scripts/evaluation/run_smoke_tests.py.

Uses the existing worker's dependencies; credentials live only in memory.
Each invocation runs one round; later rounds require an explicitly approved --resume.
--self-test checks classification without Docker, database writes or model calls.
"""

# fmt: off

import hashlib
import json
import secrets
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

IDS = (
    "data-east-delivered-revenue-2025-08",
    "data-east-sales-comparison-repair-v2",
    "data-known-region-empty-month-v7",
    "knowledge-quality-batch-evidence",
    "knowledge-margin-two-factors",
    "knowledge-receivable-risk-boundary",
    "hybrid-east-delivered-revenue-causality-boundary",
    "clarification-missing-time-range",
)
TERMINAL = {"completed", "partial", "failed", "cancelled", "needs_clarification"}


def classify(status, passed, timed_out=False):
    if timed_out:
        return "无响应"
    if passed and status in {"completed", "partial", "needs_clarification"}:
        return "成功"
    return "结果错误" if status in {"completed", "partial"} else "失败"


def emit(event, **fields):
    print(json.dumps(dict(event=event, **fields), ensure_ascii=True), flush=True)


def run_container(payload):
    import httpx
    from app.core.security import hash_password
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
    from sqlalchemy import text

    cases = [EvaluationCase.model_validate(c["case"]) for c in payload["selected"]]
    rid = "smoke-" + secrets.token_hex(8)
    resources, _ = _bootstrap_tenant(rid)
    emit("fixture", **resources)
    password = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        user = db.get(User, resources["user_id"])
        user.username, user.password_hash = rid, hash_password(password)
        db.commit()
    resources.update(_create_source_snapshot(resources, rid))
    with httpx.Client(base_url="http://api:8000/", timeout=10) as client:
        def request(method, path, expected=200, data=None):
            return _request_json(client, method, path, expected_status=expected, payload=data)

        token = request("POST", "auth/login", data={"username": rid, "password": password})
        client.headers["Authorization"] = "Bearer " + token["access_token"]
        del password, token
        document_ids = {}
        for source, content in payload["documents"].items():
            doc = request("POST", "documents", 202, {
                "name": source, "source": source, "content": content, "min_view_role": "any",
            })
            document_ids[source] = doc["id"]
            emit("document", source=source, document_id=doc["id"])
            _wait_for_document(client, document_id=doc["id"], timeout_seconds=180)
        for round_no in [payload.get("start_round", 1)]:
            round_start, results = time.monotonic(), []
            for case in cases:
                start, task, violations = time.monotonic(), {}, []
                timed_out, passed, path, uncertain = False, False, None, False
                try:
                    conversation = request("POST", "conversations", 201, {
                        "title": rid + " " + case.case_id,
                        "data_source_id": resources["data_source_id"],
                    })
                    prefix = f"conversations/{conversation['id']}"
                    accepted = request("POST", prefix + "/messages", 202, {
                        "content": case.question,
                        "document_ids": [document_ids[p] for p in case.document_scope or []],
                    })
                    path = prefix + f"/tasks/{accepted['task_id']}"
                    emit("submitted", round=round_no, case_id=case.case_id, task_id=accepted["task_id"])
                    while True:
                        remaining = 180 - (time.monotonic() - start)
                        if remaining <= 0:
                            timed_out = True
                            break
                        client.timeout = httpx.Timeout(min(10, remaining))
                        task = request("GET", path)
                        if time.monotonic() - start > 180:
                            timed_out = True
                            break
                        if task["status"] in TERMINAL:
                            break
                        time.sleep(min(2, max(0, 180 - (time.monotonic() - start))))
                    elapsed = time.monotonic() - start
                    client.timeout = httpx.Timeout(10)
                    if timed_out:
                        response = client.post(path + "/cancel")
                        if response.status_code != 200:
                            raise RuntimeError("cancellation_not_confirmed")
                    elif task["status"] != "cancelled":
                        with SessionLocal() as db:
                            db.execute(text("SET TRANSACTION READ ONLY"))
                            set_tenant_scope(db, resources["company_id"])
                            observation = observation_from_persisted_task(db, case_id=case.case_id, task_id=task["id"])
                            score = evaluate_case(case, observation)
                            passed, violations = score.passed, score.violations
                except Exception as error:  # noqa: BLE001 - redact arbitrary SDK/HTTP errors and stop.
                    elapsed = time.monotonic() - start
                    violations = [type(error).__name__]
                    uncertain = True
                    # Do not retry POST: a transport failure may already have admitted a task.
                    if path and task.get("status") not in TERMINAL:
                        client.timeout = httpx.Timeout(10)
                        client.post(path + "/cancel")
                usage = (task.get("observability") or {}).get("model_usage", {})
                budget = usage.get("budget") or {}
                cost_limit_hit = usage.get("cost") is not None and float(usage["cost"]) >= float(budget.get("max_cost", "inf"))
                row = {"round": round_no, "case_id": case.case_id, "task_id": task.get("id"),
                           "category": classify(task.get("status"), passed, timed_out),
                           "status": task.get("status", "http_error"), "stage": task.get("stage", "environment"),
                           "seconds": round(elapsed, 2), "tokens": usage.get("tokens"), "cost": usage.get("cost"),
                           "violations": violations, "error_type": task.get("error_type"), "cost_limit_hit": cost_limit_hit}
                results.append(row)
                emit("result", **row)
                if uncertain:
                    emit("stop", reason="transport_or_cancellation_uncertain")
                    return
            elapsed = time.monotonic() - round_start
            tokens = sum(r["tokens"] or 0 for r in results)
            unknown = any(r["cost"] is None for r in results)
            costs = sum(float(r["cost"] or 0) for r in results)
            emit("round", round=round_no, seconds=round(elapsed, 2), tokens=tokens,
                 cost=None if unknown else costs)
            # Unknown billing or exceeding fixture token budgets needs human review.
            if elapsed > 900 or unknown or any(r["cost_limit_hit"] or (r["tokens"] or 0) > c.max_tokens for r, c in zip(results, cases)):
                emit("stop", reason="round_time_or_usage_gate")
                return
    emit("done")


def render(payload, events):
    rows = [e for e in events if e.get("event") == "result"]
    lines = ["# 冒烟基线 " + payload["date"], "", "- Git: `" + payload["git"] + "`",
             "- 原开发用例期望未修改；oracle_review 尚为 pending，不是独立留出评测。",
             "- 隔离测试租户；经 HTTP 登录、建会话、提问、轮询，评分复用持久化 Observation。",
             "- 每题 180 秒；超时请求取消；费用沿用服务账本单位，未知不计为零。",
             "", "| 编号 | 问题原文 | 选择理由 | fixture SHA256 |", "|---|---|---|---|"]
    for item in payload["selected"]:
        c = item["case"]
        lines.append(f"| {c['case_id']} | {c['question']} | {item['purpose']} | {item['sha256']} |")
    lines += ["", "| 编号 | 第1次 | 第2次 | 第3次 | 平均秒数 | token合计 | 费用合计 |", "|---|---|---|---|---|---|---|"]
    for cid in IDS:
        found = [r for r in rows if r["case_id"] == cid]
        cells = [next((r["category"] for r in found if r["round"] == n), "未运行") for n in range(1, 4)]
        avg = f"{sum(r['seconds'] for r in found)/len(found):.2f}" if found else "未知"
        tokens = str(sum(r["tokens"] for r in found)) if found and all(r["tokens"] is not None for r in found) else "未知"
        cost = str(sum(float(r["cost"]) for r in found)) if found and all(r["cost"] is not None for r in found) else "未知"
        lines.append(f"| {cid} | " + " | ".join(cells) + f" | {avg} | {tokens} | {cost} |")
    counts = Counter(r["category"] for r in rows)
    lines += ["", "- 四类汇总：" + str({k: counts[k] for k in ("成功", "结果错误", "失败", "无响应")}),
              "", "| 轮次 | 用例 | task_id | 状态/阶段 | 秒数 | tokens | cost | 评分差异/异常类型 |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['round']} | {r['case_id']} | {r['task_id']} | {r['status']}/{r['stage']} | {r['seconds']} | {r['tokens']} | {r['cost']} | {','.join(r['violations'])}; {r['error_type']} |")
    lines += ["", "## 执行事件（不含凭据）", ""]
    lines += ["- " + json.dumps(e, ensure_ascii=False) for e in events if e.get("event") in {"fixture", "round", "stop", "done", "fatal"}]
    return "\n".join(lines) + "\n"


def main():
    root = Path(__file__).resolve().parents[3]
    selection = json.loads((root / "docs/design/development_case_selection.json").read_text(encoding="utf-8"))
    payload = {"selected": [], "documents": {}, "date": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
                   "git": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()}
    corpus = root / "data/business_knowledge_base"
    hashes = {a["path"]: a["sha256"] for a in json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))["artifacts"]}
    for cid in IDS:
        selected = next(c for c in selection["cases"] if c["case_id"] == cid)
        file = root / "backend/tests/fixtures/evaluation" / selected["file"]
        raw = file.read_bytes()
        case = next(c for c in json.loads(raw)["cases"] if c["case_id"] == cid)
        payload["selected"].append({"case": case, "purpose": selected["purpose"], "sha256": hashlib.sha256(raw).hexdigest()})
        for source in case.get("document_scope") or []:
            raw_doc = (corpus / source).read_bytes()
            if hashlib.sha256(raw_doc).hexdigest() != hashes[source]:
                raise ValueError("corpus manifest mismatch")
            payload["documents"][source] = raw_doc.decode("utf-8")
    output = root / "docs/smoke_results" / (payload["date"] + ".md")
    state = root / "artifacts/smoke" / (payload["date"] + ".json")
    events = []
    if "--resume" in sys.argv:
        events = json.loads(state.read_text(encoding="utf-8"))
        rounds = [e["round"] for e in events if e.get("event") == "round"]
        payload["start_round"] = max(rounds, default=0) + 1
        count = sum(e.get("event") == "result" for e in events)
        if not rounds or count != max(rounds) * 8 or payload["start_round"] > 3:
            raise ValueError("Resume requires complete prior rounds and remaining task budget")
    elif output.exists() or state.exists():
        raise FileExistsError("Refusing to overwrite prior smoke results")
    output.parent.mkdir(parents=True, exist_ok=True)
    state.parent.mkdir(parents=True, exist_ok=True)
    code = Path(__file__).read_text(encoding="utf-8")
    process = subprocess.Popen(["docker", "exec", "-i", "-e", "PYTHONDONTWRITEBYTECODE=1", "agent-worker-1", "python", "-u", "-c", code, "--container"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    process.stdin.write(json.dumps(payload))
    process.stdin.close()
    for line in process.stdout:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # Runtime logs may include sensitive error details; never persist them.
        if not isinstance(event, dict) or "event" not in event:
            continue
        events.append(event)
        state.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        output.write_text(render(payload, events), encoding="utf-8")
        print(json.dumps(event, ensure_ascii=True), flush=True)
    rc = process.wait()
    if rc or not events or events[-1].get("event") != "done":
        print("STOP: inspect the recorded gate; do not automatically rerun.")
        return 1
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        assert classify("completed", True) == "成功"
        assert classify("partial", False) == "结果错误"
        assert classify("needs_clarification", True) == "成功"
        assert classify("failed", False) == "失败"
        assert classify("running", False, True) == "无响应"
        print("5 classification assertions passed")
    elif "--container" in sys.argv:
        try:
            run_container(json.load(sys.stdin))
        except Exception as error:  # noqa: BLE001 - never expose credentials through a traceback.
            emit("fatal", error_type=type(error).__name__)
            sys.exit(1)
    else:
        sys.exit(main())
