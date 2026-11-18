"""Authentication token revocation records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.extensions import db
from backend.app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class TokenRevocation(UUIDPrimaryKeyMixin, CreatedAtMixin, db.Model):
    __tablename__ = "token_revocations"

    jti: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    token_type: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
