from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class TaskSpec(Base):
    __tablename__ = "taskspecs"
    id: Mapped[int] = mapped_column(primary_key=True)
