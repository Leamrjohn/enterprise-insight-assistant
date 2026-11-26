"""M1: the runtime context a tool service trusts only when the worker signed it.

A hash anyone can recompute proves nothing about who sent a request.  An HMAC
needs the shared key, so a caller without it cannot change the company, the role
or the document scope.  The signature proves origin, not current permission: the
service still re-checks membership and document visibility in the database.
"""

import hashlib
import hmac
import json
from dataclasses import asdict, dataclass

CONTEXT_VERSION = "tool-runtime-context/v1"


@dataclass(frozen=True)
class RuntimeContext:
    task_id: int
    execution_id: str
    actor_id: int
    authorized_role: str
    company_id: int
    document_scope_sha256: str
    expires_at: int  # Unix seconds; signed with everything else.


class ContextRejected(Exception):
    """The tool service must not run the call; code is an ERROR_CLASSES entry."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def issue(
    *,
    task_id: int,
    execution_id: str,
    actor_id: int,
    authorized_role: str,
    company_id: int,
    document_scope_sha256: str,
    now: int,
    ttl_seconds: int,
) -> RuntimeContext:
    return RuntimeContext(
        task_id=task_id,
        execution_id=execution_id,
        actor_id=actor_id,
        authorized_role=authorized_role,
        company_id=company_id,
        document_scope_sha256=document_scope_sha256,
        expires_at=now + ttl_seconds,
    )


def document_scope_sha256(company_id: int, document_ids: list[int] | None) -> str:
    """Bind a context to exactly the documents one call may read (order ignored)."""
    payload = {
        "company_id": company_id,
        "document_ids": sorted(document_ids) if document_ids is not None else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _canonical(context: RuntimeContext) -> bytes:
    # Sorted keys and fixed separators: both sides must sign the same bytes.
    payload = {"version": CONTEXT_VERSION, **asdict(context)}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def sign(context: RuntimeContext, key: bytes) -> str:
    return hmac.new(key, _canonical(context), hashlib.sha256).hexdigest()


def verify(context: RuntimeContext, signature: str, key: bytes, *, now: int) -> None:
    """Return if the worker signed this context and it has not expired.

    Raise ContextRejected("tool_context_signature_invalid") for a wrong signature,
    then ContextRejected("tool_context_expired") once now reaches expires_at.
    The signature comes first: expires_at means nothing until it is proven signed.
    """
    if not hmac.compare_digest(sign(context, key), signature):
        raise ContextRejected("tool_context_signature_invalid")
    if now >= context.expires_at:
        raise ContextRejected("tool_context_expired")
