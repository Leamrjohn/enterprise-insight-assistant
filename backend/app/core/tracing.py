"""Distributed tracing with OpenTelemetry (O1).

One trace follows a question from the API request through the worker, every
workflow node, tool call and model call.  The API stores the W3C
``traceparent`` on the task row (``analysis_tasks.trace_context``); the worker
continues that trace, so a resumed attempt shares the trace id.

Spans carry only allowlisted attribute keys (``safe_attributes``): ids, names,
model names, outcomes.  Never questions, answers, SQL, prompts, document text
or tool arguments.  The collector drops other keys a second time.

Export is off unless ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (standard
OpenTelemetry variable); spans and trace ids exist either way, and losing the
collector never affects a task: workflow events and the ledger stay the
source of truth.
"""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, TypeVar

from opentelemetry import context, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

TRACER_NAME = "agent-platform"
ALLOWED_ATTRIBUTES = frozenset(
    {
        "task_id",
        "execution_id",
        "company_id",  # in traces only, never a metric label
        "node",
        "resumed",
        "queue_seconds",
        "tool.name",
        "tool.version",
        "tool.outcome",
        "error.class",
        "gen_ai.system",
        "gen_ai.request.model",
        "gen_ai.response.finish_reason",
        "http.request.method",
        "http.route",
        "http.response.status_code",
    }
)
_propagator = TraceContextTextMapPropagator()
_provider: TracerProvider | None = None


def safe_attributes(
    attributes: Mapping[str, object],
) -> dict[str, str | int | float | bool]:
    """Keep allowlisted keys with scalar values; drop everything else."""
    safe: dict[str, str | int | float | bool] = {}
    for key, value in attributes.items():
        if key in ALLOWED_ATTRIBUTES and isinstance(value, str | int | float | bool):
            safe[key] = value
    return safe


def setup_tracing(
    service_name: str, *, processor: SpanProcessor | None = None
) -> TracerProvider:
    """Create this process's tracer provider.  The batch processor restarts its
    thread after a fork, so Celery's pool children need no setup of their own;
    tests pass an in-memory ``processor`` instead of the OTLP exporter."""
    global _provider
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if processor is not None:
        provider.add_span_processor(processor)
    elif os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    if _provider is None:
        trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def tracer() -> trace.Tracer:
    if _provider is not None:
        return _provider.get_tracer(TRACER_NAME)
    return trace.get_tracer(TRACER_NAME)


def current_traceparent() -> str | None:
    carrier: dict[str, str] = {}
    _propagator.inject(carrier)
    return carrier.get("traceparent")


@contextmanager
def span(
    name: str,
    *,
    traceparent: str | None = None,
    attributes: Mapping[str, object] | None = None,
) -> Iterator[Span]:
    """A span with allowlisted attributes; ``traceparent`` continues a stored
    trace (the worker side of a task).  Exceptions mark the span and re-raise."""
    parent = _propagator.extract({"traceparent": traceparent}) if traceparent else None
    token = context.attach(parent) if parent is not None else None
    try:
        with tracer().start_as_current_span(
            name,
            attributes=safe_attributes(attributes or {}),
            record_exception=False,
            set_status_on_exception=False,
        ) as current:
            try:
                yield current
            except BaseException as exc:
                current.set_attribute("error.class", type(exc).__name__)
                current.set_status(Status(StatusCode.ERROR))
                raise
    finally:
        if token is not None:
            context.detach(token)


def set_attributes(current: Span, attributes: Mapping[str, object]) -> None:
    current.set_attributes(safe_attributes(attributes))


F = TypeVar("F", bound=Callable[..., Any])


def traced_model_call(system: str) -> Callable[[F], F]:
    """One ``gen_ai.chat`` span per physical provider call.  Token counts per
    call are left to C2 (measurement) and are not recorded here yet."""

    def decorate(method: F) -> F:
        @functools.wraps(method)
        def run(self, *args, **kwargs):
            with span(
                "gen_ai.chat",
                attributes={
                    "gen_ai.system": system,
                    "gen_ai.request.model": getattr(self, "model_name", None),
                },
            ):
                return method(self, *args, **kwargs)

        return run  # type: ignore[return-value]

    return decorate
