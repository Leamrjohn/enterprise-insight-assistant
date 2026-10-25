from app.db.base import Base
from sqlalchemy.orm import Mapped, mapped_column


class TaskSpec(Base):
    __tablename__ = "taskspecs"
    id: Mapped[int] = mapped_column(primary_key=True)
