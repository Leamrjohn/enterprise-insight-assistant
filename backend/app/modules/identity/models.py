from datetime import datetime

from app.core.security import hash_api_key
from app.db.base import Base
from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auth_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    api_key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def api_key(self) -> str | None:
        """Compatibility helper for newly-created test and bootstrap users.

        Plain API keys are deliberately never loaded from the database.  The
        value exists only on the in-memory object that originally received it.
        """
        return getattr(self, "_plain_api_key", None)

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._plain_api_key = value
        self.api_key_hash = hash_api_key(value)
