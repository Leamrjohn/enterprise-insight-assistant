"""Database-authoritative timestamps for cross-process lease decisions."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def database_now(db: Session) -> datetime:
    current = db.scalar(select(func.clock_timestamp()))
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise RuntimeError("database did not return an aware timestamp")
    return current
