"""M1: the agent-tools service.  Every call proves who sent it before anything runs.

Order matters and is fixed: verify the signature, then re-check the database
(task, execution, membership), then the tool's own scope check, then execute.
A forged request never reaches the database, and a signed one for a user who
has since lost access never reaches the tool.
"""

import time
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, fields
from functools import lru_cache
from typing import Any

from mcp.server import MCPServer
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.db.session import SessionLocal, set_tenant_scope
from app.modules.runtime.tools.authorization import (
    current_member_allowed,
    documents_still_visible,
)
from app.modules.runtime.tools.catalog import ANALYSIS_ROLES
from app.modules.runtime.tools.context import (
    ContextRejected,
    RuntimeContext,
    document_scope_sha256,
    verify,
)
from app.modules.runtime.tools.wire import encode
from app.modules.workflow.models import AnalysisTask

SERVER_NAME = "agent-tools"
SERVER_VERSION = "1.0.0"
SERVER_PORT = 8090

ToolHandler = Callable[[dict[str, Any]], Any]
ScopeCheck = Callable[[Session, RuntimeContext, dict[str, Any]], None]
Prepare = Callable[[Session, RuntimeContext], ToolHandler]


@dataclass(frozen=True)
class ServiceTool:
    """A handler returns plain data or a ToolOutput; check raises ContextRejected.

    M3: prepare builds the handler from what the task holds, such as its company
    data source, so nothing in the arguments can choose it.  check and prepare
    run inside the database session; the handler runs after it closes.
    """

    run: ToolHandler | None = None
    check: ScopeCheck | None = None
    prepare: Prepare | None = None

    def __post_init__(self) -> None:
        if (self.run is None) == (self.prepare is None):
            raise ValueError("a service tool needs exactly one of run and prepare")


def _echo(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"echo": arguments.get("text", "")}


def check_rag_scope(
    db: Session, context: RuntimeContext, arguments: dict[str, Any]
) -> None:
    """M2: the documents searched are the signed ones and still visible to the user."""
    document_ids = arguments.get("document_ids")
    if arguments.get("company_id") != context.company_id or not isinstance(
        document_ids, list
    ):
        raise ContextRejected("tool_company_scope_denied")
    if document_scope_sha256(context.company_id, document_ids) != (
        context.document_scope_sha256
    ):
        raise ContextRejected("tool_document_scope_denied")
    if not documents_still_visible(
        db,
        company_id=context.company_id,
        user_id=context.actor_id,
        document_ids=document_ids,
    ):
        raise ContextRejected("tool_document_current_authorization_denied")


@lru_cache(maxsize=1)
def _rag_tool() -> Any:
    # Built once per process; main() loads its models before the first call.
    from app.modules.knowledge.tool import RAGTool

    return RAGTool()


def warm_up() -> None:
    """M2b: load the embedding and rerank models before serving.

    Loading takes longer than the worker's call timeout, so loading on the first
    call would fail the first search after every restart.
    """
    from app.core.settings import get_settings
    from app.modules.knowledge.rag.embeddings_local import LocalEmbeddingProvider
    from app.modules.knowledge.rag.reranker import LocalCrossEncoderReranker

    LocalEmbeddingProvider()
    LocalCrossEncoderReranker(get_settings().reranker_model).score("预热", ["预热"])
    _rag_tool()


def _rag_search(arguments: dict[str, Any]) -> Any:
    from app.modules.analysis.tool_protocol import ToolInput

    return _rag_tool().execute(ToolInput(parameters=arguments))


def task_data_source(db: Session, context: RuntimeContext) -> Any:
    """M3: the company data source and schema the task froze at admission.

    The same checks the worker makes before it builds SQLTool (workflow/tasks.py).
    """
    from app.modules.organizations.models import BusinessDataSource, SchemaSnapshot

    task = db.get(AnalysisTask, context.task_id)
    if task is None or task.data_source_id is None or task.schema_snapshot_id is None:
        raise ContextRejected("data_source_not_allowed")
    source = db.get(BusinessDataSource, task.data_source_id)
    snapshot = db.get(SchemaSnapshot, task.schema_snapshot_id)
    if (
        source is None
        or snapshot is None
        or snapshot.data_source_id != source.id
        or source.company_id != context.company_id
    ):
        raise ContextRejected("data_source_not_allowed")
    # Load the connection row now: the query runs after this session closes.
    _ = source.connection
    return source, snapshot.catalog


def prepare_sql_query(db: Session, context: RuntimeContext) -> ToolHandler:
    from app.modules.analysis.catalog.snapshot_catalog import SnapshotCatalog
    from app.modules.analysis.data.sql_tool import SQLTool
    from app.modules.analysis.tool_protocol import ToolInput

    source, catalog = task_data_source(db, context)
    tool = SQLTool(
        data_source=source, snapshot_catalog=SnapshotCatalog.from_snapshot(catalog)
    )
    return lambda arguments: tool.execute(ToolInput(parameters=arguments))


def prepare_template_query(db: Session, context: RuntimeContext) -> ToolHandler:
    from app.modules.analysis.data.template_query import TemplateQueryTool
    from app.modules.analysis.tool_protocol import ToolInput

    source, _catalog = task_data_source(db, context)
    tool = TemplateQueryTool(data_source=source)
    return lambda arguments: tool.execute(ToolInput(parameters=arguments))


DEFAULT_TOOLS: Mapping[str, ToolHandler | ServiceTool] = {
    "echo": _echo,
    "rag_search": ServiceTool(run=_rag_search, check=check_rag_scope),
    "sql_query": ServiceTool(prepare=prepare_sql_query),
    "template_query": ServiceTool(prepare=prepare_template_query),
}


def _reply(result: Any) -> dict[str, Any]:
    from app.modules.analysis.tool_protocol import ToolOutput

    if not isinstance(result, ToolOutput):
        return {"success": True, "data": encode(result)}
    if result.success:
        # M3: Decimal, date and tuple values cross as marked JSON (wire.py).
        return {"success": True, "data": encode(result.data)}
    return {
        "success": False,
        "error_code": result.error_code,
        "error": result.error,
        "repairable": result.repairable,
        "model_feedback": result.model_feedback,
    }


def _parse_context(raw: Any) -> RuntimeContext:
    names = {field.name for field in fields(RuntimeContext)}
    if not isinstance(raw, dict) or set(raw) != names:
        # A malformed context cannot have been signed by the worker.
        raise ContextRejected("tool_context_signature_invalid")
    try:
        return RuntimeContext(**raw)
    except TypeError as error:
        raise ContextRejected("tool_context_signature_invalid") from error


def authorize(
    db: Session, raw_context: Any, signature: str, *, key: bytes, now: int
) -> RuntimeContext:
    """Return the context only if it is signed, current, and the user still may act."""
    context = _parse_context(raw_context)
    verify(context, signature, key, now=now)
    # Only now is company_id trusted enough to scope the database session.
    set_tenant_scope(db, context.company_id)
    task = db.get(AnalysisTask, context.task_id)
    if (
        task is None
        or task.company_id != context.company_id
        or task.user_id != context.actor_id
        # A worker whose lease was taken over must not keep calling tools.
        or task.active_execution_id != context.execution_id
        or not current_member_allowed(
            db,
            company_id=context.company_id,
            user_id=context.actor_id,
            allowed_roles=ANALYSIS_ROLES,
        )
    ):
        raise ContextRejected("tool_current_authorization_denied")
    return context


def create_tool_server(
    *,
    signing_key: bytes,
    session_factory: Callable[[], AbstractContextManager[Session]] = SessionLocal,
    clock: Callable[[], float] = time.time,
    tools: Mapping[str, ToolHandler | ServiceTool] = DEFAULT_TOOLS,
) -> MCPServer:
    server = MCPServer(SERVER_NAME, version=SERVER_VERSION)

    def register(name: str, tool: ServiceTool) -> None:
        @server.tool(name=name, description=f"agent-tools: {name}")
        def call(
            arguments: dict[str, Any], context: dict[str, Any], signature: str
        ) -> dict[str, Any]:
            with session_factory() as db:
                try:
                    trusted = authorize(
                        db, context, signature, key=signing_key, now=int(clock())
                    )
                    if tool.check is not None:
                        tool.check(db, trusted, arguments)
                    handler = (
                        tool.prepare(db, trusted)
                        if tool.prepare is not None
                        else tool.run
                    )
                except ContextRejected as rejected:
                    return {"success": False, "error_code": rejected.code}
            assert handler is not None, "ServiceTool requires run or prepare"
            return _reply(handler(arguments))

    for name, tool in tools.items():
        register(name, tool if isinstance(tool, ServiceTool) else ServiceTool(run=tool))

    @server.custom_route("/health/live", methods=["GET"])
    async def health(request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    return server


def main() -> None:
    import uvicorn

    from app.core.settings import get_settings

    key = get_settings().tool_context_signing_key.get_secret_value().encode()
    warm_up()  # the port opens, and the health check passes, only once models load
    app = create_tool_server(signing_key=key).streamable_http_app(
        stateless_http=True, json_response=True, host="0.0.0.0"
    )
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)


if __name__ == "__main__":
    main()
