import time
from contextlib import nullcontext
from dataclasses import replace

import pytest
from app.modules.identity.models import User
from app.modules.organizations.models import Company, CompanyMember
from app.modules.runtime.tools.context import RuntimeContext, issue
from app.modules.runtime.tools.mcp_client import call_tool
from app.modules.workflow.models import AnalysisTask
from app.tool_service.server import create_tool_server

KEY = b"worker-and-tool-service-share-this"
NOW = 1_800_000_000


@pytest.fixture
def seeded(db_session):
    user = User(name="tool-server-user", api_key="tool-server-key")
    company = Company(name="tool-server-company")
    other = Company(name="tool-server-other")
    db_session.add_all([user, company, other])
    db_session.flush()
    member = CompanyMember(company_id=company.id, user_id=user.id, role="analyst")
    task = AnalysisTask(
        user_id=user.id,
        company_id=company.id,
        question="回声",
        status="running",
        stage="querying_data",
        active_execution_id="exec-1",
    )
    db_session.add_all([member, task])
    db_session.flush()
    return {
        "user": user,
        "company": company,
        "other": other,
        "task": task,
        "member": member,
    }


@pytest.fixture
def executed():
    return []


@pytest.fixture
def server(db_session, executed):
    def echo(arguments):
        executed.append(arguments)
        return {"echo": arguments["text"]}

    return create_tool_server(
        signing_key=KEY,
        session_factory=lambda: nullcontext(db_session),
        clock=lambda: NOW,
        tools={"echo": echo},
    )


def _context(seeded, **overrides) -> RuntimeContext:
    return replace(
        issue(
            task_id=seeded["task"].id,
            execution_id="exec-1",
            actor_id=seeded["user"].id,
            authorized_role="analyst",
            company_id=seeded["company"].id,
            document_scope_sha256="a" * 64,
            now=NOW,
            ttl_seconds=60,
        ),
        **overrides,
    )


def _call(server, context, *, key=KEY):
    return call_tool(
        server, "echo", {"text": "你好"}, context, key=key, timeout_seconds=5
    )


def test_signed_call_from_a_current_member_runs(server, seeded, executed):
    result = _call(server, _context(seeded))

    assert result.success
    assert result.data == {"echo": "你好"}
    assert executed == [{"text": "你好"}]


def test_forged_signature_never_runs(server, seeded, executed):
    result = _call(server, _context(seeded), key=b"guessed-key")

    assert result.error_code == "tool_context_signature_invalid"
    assert executed == []


def test_expired_context_never_runs(server, seeded, executed):
    result = _call(server, _context(seeded, expires_at=NOW))

    assert result.error_code == "tool_context_expired"
    assert executed == []


def test_other_company_never_runs(server, seeded, executed):
    # Validly signed, but the user is not a member there and the task is not theirs.
    result = _call(server, _context(seeded, company_id=seeded["other"].id))

    assert result.error_code == "tool_current_authorization_denied"
    assert executed == []


def test_removed_member_never_runs_even_with_a_valid_signature(
    db_session, server, seeded, executed
):
    seeded["member"].status = "removed"
    db_session.flush()

    result = _call(server, _context(seeded))

    assert result.error_code == "tool_current_authorization_denied"
    assert executed == []


def test_taken_over_execution_never_runs(db_session, server, seeded, executed):
    seeded["task"].active_execution_id = "exec-2"
    db_session.flush()

    result = _call(server, _context(seeded))

    assert result.error_code == "tool_current_authorization_denied"
    assert executed == []


def test_unreachable_service_fails_clearly_within_the_timeout(seeded):
    started = time.monotonic()

    result = call_tool(
        "http://127.0.0.1:9/mcp",
        "echo",
        {"text": "你好"},
        _context(seeded),
        key=KEY,
        timeout_seconds=2,
    )

    assert result.error_code == "mcp_transport_unavailable"
    assert time.monotonic() - started < 3
