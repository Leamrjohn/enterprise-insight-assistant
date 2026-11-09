"""K1: settings split by domain keep every default and every validator."""

from collections import Counter

import pytest
from app.core.config.rag import RagConfig
from app.core.config.settings import DOMAINS, Settings
from app.modules.runtime.tool_loop import LoopLimits
from pydantic import ValidationError

REQUIRED = {"database_password": "x", "business_database_password": "y"}

# The code constants K1 moved into configuration, with their values before K1.
MOVED_CONSTANT_DEFAULTS = {
    "rate_limit_max_requests": 100,  # core/middleware.py RATE_LIMIT_MAX
    "rate_limit_window_seconds": 60,  # RATE_LIMIT_WINDOW
    "planner_max_attempts": 2,  # planning.py MAX_PLANNER_ATTEMPTS
    "data_max_attempts": 2,  # data_agent.py MAX_DATA_ATTEMPTS
    "context_history_max_tokens": 2048,  # conversations MAX_CONTEXT_TOKENS
    "context_compress_at": 0.8,  # context_budget.py COMPRESS_AT
    "context_max_rows_when_compressed": 20,
    "context_max_chunk_chars_when_compressed": 800,
    "memory_planner_max_tokens": 1024,  # memory MAX_PLANNER_MEMORY_TOKENS
    "memory_ttl_days": 30,  # DEFAULT_MEMORY_TTL
    "memory_soft_delete_retention_days": 90,  # SOFT_DELETE_RETENTION
    "rag_rrf_k": 60,  # retrieval.py RRF_K
    "tool_loop_max_rounds": 6,  # LoopLimits defaults
    "tool_loop_max_tool_calls": 8,
    "tool_loop_max_repairs": 2,
    "tool_loop_max_seconds": 90.0,
    "tool_loop_model_retries": 1,
    "tool_loop_backoff_seconds": 1.0,
    "knowledge_tool_loop_max_rounds": 4,  # Knowledge LoopLimits(4, 5)
    "knowledge_tool_loop_max_tool_calls": 5,
}


def test_moved_constants_keep_their_old_values():
    settings = Settings(**REQUIRED)

    assert {
        name: getattr(settings, name) for name in MOVED_CONSTANT_DEFAULTS
    } == MOVED_CONSTANT_DEFAULTS
    assert LoopLimits() == LoopLimits(6, 8, 2, 90.0, 1, 1.0)


def test_every_field_belongs_to_exactly_one_domain():
    owners = Counter(name for domain in DOMAINS for name in domain.model_fields)

    assert [name for name, count in owners.items() if count > 1] == []
    assert set(owners) == set(Settings.model_fields)


def test_domain_methods_do_not_shadow_each_other():
    # Settings inherits every domain; two domains defining the same validator
    # name would silently drop one of them.
    names = Counter(
        name
        for domain in DOMAINS
        for name, value in vars(domain).items()
        if callable(value) or isinstance(value, classmethod | property)
    )

    assert [name for name, count in names.items() if count > 1] == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_pool_size", 0),
        ("rate_limit_max_requests", 0),
        ("analysis_task_global_inflight_limit", 0),
        ("planner_max_attempts", 0),
        ("tool_loop_max_rounds", 0),
        ("context_compress_at", 1.5),
        ("memory_ttl_days", 0),
        ("rag_rrf_k", 0),
        ("input_artifact_pdf_max_ocr_pages", 0),
    ],
)
def test_each_domain_validator_runs_on_settings(field, value):
    with pytest.raises(ValidationError, match=field):
        Settings(**REQUIRED, **{field: value})


def test_domain_returns_one_domains_values():
    settings = Settings(**REQUIRED, rag_rerank_top_k=5)

    rag = settings.domain(RagConfig)

    assert isinstance(rag, RagConfig)
    assert rag.rag_rerank_top_k == 5
    assert set(rag.model_dump()) == set(RagConfig.model_fields)
