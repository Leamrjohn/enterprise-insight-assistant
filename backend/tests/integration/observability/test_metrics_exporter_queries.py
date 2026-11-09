"""O2a: the exporter's queries run on the migrated schema, read-only."""

import pytest
from app.modules.observability.metrics_exporter import (
    PlatformCollector,
    read_only_engine,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


@pytest.fixture
def engine():
    engine = read_only_engine()
    yield engine
    engine.dispose()


def test_collector_reads_the_schema(engine, tmp_path):
    families = {
        family.name: family for family in PlatformCollector(engine, tmp_path).collect()
    }

    assert families["agent_exporter_up"].samples[0].value == 1
    assert {
        "agent_tasks_inflight",
        "agent_outbox_pending_age_seconds",
        "agent_leases_expired",
        "agent_tasks_stranded",
        "agent_reserved_billing_stale",
    } <= set(families)


def test_exporter_connections_cannot_write(engine):
    with engine.connect() as connection, pytest.raises(DBAPIError, match="read-only"):
        connection.execute(text("CREATE TEMP TABLE exporter_write_probe (id int)"))
