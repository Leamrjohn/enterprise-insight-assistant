from dataclasses import replace

import pytest
from app.core.config.settings import Settings
from app.modules.runtime.tools.context import (
    ContextRejected,
    RuntimeContext,
    issue,
    sign,
    verify,
)
from app.modules.runtime.tools.errors import ErrorClass, classify

KEY = b"worker-and-tool-service-share-this"
NOW = 1_800_000_000


def _context(**overrides) -> RuntimeContext:
    values = {
        "task_id": 7,
        "execution_id": "exec-1",
        "actor_id": 3,
        "authorized_role": "analyst",
        "company_id": 1,
        "document_scope_sha256": "a" * 64,
        "now": NOW,
        "ttl_seconds": 60,
    }
    values.update(overrides)
    return issue(**values)


def _rejected_code(context, signature, *, key=KEY, now=NOW) -> str:
    with pytest.raises(ContextRejected) as caught:
        verify(context, signature, key, now=now)
    return caught.value.code


def test_issue_sets_expiry_from_ttl():
    assert _context().expires_at == NOW + 60


def test_signed_context_is_accepted_until_it_expires():
    context = _context()

    verify(context, sign(context, KEY), KEY, now=NOW)
    verify(context, sign(context, KEY), KEY, now=NOW + 59)


@pytest.mark.parametrize(
    "tampered",
    [
        {"company_id": 2},
        {"authorized_role": "owner"},
        {"actor_id": 4},
        {"task_id": 8},
        {"execution_id": "exec-2"},
        {"document_scope_sha256": "b" * 64},
        # Extending its own lifetime is tampering too.
        {"expires_at": NOW + 3600},
    ],
)
def test_changing_any_field_after_signing_is_rejected(tampered):
    context = _context()
    signature = sign(context, KEY)

    code = _rejected_code(replace(context, **tampered), signature)

    assert code == "tool_context_signature_invalid"


def test_a_signature_made_without_the_key_is_rejected():
    context = _context()

    assert _rejected_code(context, sign(context, b"guessed-key")) == (
        "tool_context_signature_invalid"
    )
    assert _rejected_code(context, "") == "tool_context_signature_invalid"
    assert _rejected_code(context, "0" * 64) == "tool_context_signature_invalid"


def test_an_expired_context_is_rejected():
    context = _context()

    assert _rejected_code(context, sign(context, KEY), now=NOW + 60) == (
        "tool_context_expired"
    )


def test_signature_is_checked_before_expiry():
    # A forged context with a far-future expiry must fail as forged, not as valid.
    context = replace(_context(), expires_at=NOW - 1)

    assert _rejected_code(context, "f" * 64) == "tool_context_signature_invalid"


def test_rejections_are_denials():
    assert classify("tool_context_signature_invalid") is ErrorClass.DENIED
    assert classify("tool_context_expired") is ErrorClass.DENIED


def test_development_signing_key_refuses_production():
    required = {
        "database_password": "x",
        "business_database_password": "x",
        "jwt_secret": "a-real-secret",
    }
    with pytest.raises(ValueError, match="TOOL_CONTEXT_SIGNING_KEY"):
        Settings(**required, app_env="production")

    Settings(**required, app_env="production", tool_context_signing_key="a-real-key")
