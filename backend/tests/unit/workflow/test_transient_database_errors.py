"""3.6: a brief platform-database outage must be retried, not turned into a business failure."""

import pytest
from app.db.errors import is_transient_database_error
from app.modules.analysis.agent_protocol import AgentInput
from app.modules.analysis.planner.planner_agent import PlannerAgent
from app.modules.workflow.tasks import _is_retryable_exception
from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    PendingRollbackError,
    ProgrammingError,
)


def _driver_error(message: str) -> Exception:
    return Exception(message)


CONNECTION_LOST = OperationalError(
    "SELECT 1", {}, _driver_error("server closed the connection unexpectedly")
)


@pytest.mark.parametrize(
    "exc",
    [
        CONNECTION_LOST,
        InterfaceError("SELECT 1", {}, _driver_error("connection already closed")),
        DBAPIError(
            "SELECT 1",
            {},
            _driver_error("terminating connection"),
            connection_invalidated=True,
        ),
    ],
)
def test_connection_level_database_errors_are_transient(exc: Exception) -> None:
    assert is_transient_database_error(exc) is True
    assert _is_retryable_exception(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        IntegrityError("INSERT", {}, _driver_error("duplicate key")),
        ProgrammingError("SELECT", {}, _driver_error("column does not exist")),
        # Cause is unknown from the exception alone; retrying could repeat a permanent error.
        PendingRollbackError("rollback first"),
        ValueError("not a database error"),
    ],
)
def test_non_connection_database_errors_are_not_retried(exc: Exception) -> None:
    assert is_transient_database_error(exc) is False
    assert _is_retryable_exception(exc) is False


class _DatabaseDownPlanning:
    model_attempts = 0

    def decide(self, question, **kwargs):
        raise CONNECTION_LOST


def test_planner_propagates_database_outage_instead_of_business_failure() -> None:
    agent = PlannerAgent(planning_service=_DatabaseDownPlanning())

    with pytest.raises(OperationalError):
        agent.run(AgentInput(question="华东区8月销售额是多少？", user_id=1))


def _raised_during(handling: Exception, raised: Exception) -> Exception:
    """Reproduce Python's implicit chaining: `raised` occurs while handling `handling`."""
    try:
        try:
            raise handling
        except type(handling):
            raise raised
    except type(raised) as chained:
        return chained


def test_pending_rollback_caused_by_lost_connection_is_transient() -> None:
    """Seen in drill 4c: logging the failed call reused the dead session."""
    chained = _raised_during(CONNECTION_LOST, PendingRollbackError("rollback first"))

    assert is_transient_database_error(chained) is True
    assert _is_retryable_exception(chained) is True


def test_pending_rollback_caused_by_constraint_error_stays_permanent() -> None:
    chained = _raised_during(
        IntegrityError("INSERT", {}, _driver_error("duplicate key")),
        PendingRollbackError("rollback first"),
    )

    assert is_transient_database_error(chained) is False


def test_planner_propagates_pending_rollback_from_lost_connection() -> None:
    class _Planning:
        model_attempts = 0

        def decide(self, question, **kwargs):
            raise _raised_during(CONNECTION_LOST, PendingRollbackError("rollback"))

    with pytest.raises(PendingRollbackError):
        PlannerAgent(planning_service=_Planning()).run(
            AgentInput(question="华东区8月销售额是多少？", user_id=1)
        )
