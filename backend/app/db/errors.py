"""Classify platform-database failures that a retry can reasonably fix."""

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

_MAX_CHAIN_DEPTH = 8


def _is_connection_failure(exc: BaseException) -> bool:
    if isinstance(exc, (OperationalError, InterfaceError)):
        return True
    return isinstance(exc, DBAPIError) and bool(exc.connection_invalidated)


def is_transient_database_error(exc: BaseException) -> bool:
    """True when a lost or invalidated connection is the root of this failure.

    The exception chain is followed because the visible error is often a
    secondary one: after a restart, logging the failed call on the same session
    raises PendingRollbackError with the OperationalError as its context.
    Constraint, syntax and data errors repeat identically on retry, so a
    PendingRollbackError caused by one of those is still not transient.
    """
    current: BaseException | None = exc
    for _ in range(_MAX_CHAIN_DEPTH):
        if current is None:
            return False
        if _is_connection_failure(current):
            return True
        current = current.__cause__ or current.__context__
    return False
