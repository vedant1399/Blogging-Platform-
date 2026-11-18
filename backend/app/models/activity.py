"""Post analytics events and moderation reports."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.extensions import db
from backend.app.models.enums import AnalyticsEventType, ReportStatus, ReportTargetType
from backend.app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.models.post import Post
    from backend.app.models.user import User


class PostAnalyticsEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, db.Model):
    __tablename__ = "post_analytics_events"
    __table_args__ = (
        CheckConstraint("reading_time_seconds >= 0", name="reading_time_nonnegative"),
        Index("ix_post_events_post_created", "post_id", "created_at"),
        Index("ix_post_events_type_created", "event_type", "created_at"),
    )

    post_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    visitor_key_hash: Mapped[str | None] = mapped_column(String(64))
    event_type: Mapped[AnalyticsEventType] = mapped_column(
        Enum(
            AnalyticsEventType,
            name="analytics_event_type",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [member.value for member in enum_type],
        ),
        nullable=False,
    )
    reading_time_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    post: Mapped[Post] = relationship()
    actor: Mapped[User | None] = relationship()


class Report(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_status_created", "status", "created_at"),
    )

    reporter_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[ReportTargetType] = mapped_column(
        Enum(
            ReportTargetType,
            name="report_target_type",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [member.value for member in enum_type],
        ),
        nullable=False,
    )
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(
            ReportStatus,
            name="report_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [member.value for member in enum_type],
        ),
        nullable=False,
        default=ReportStatus.PENDING,
    )
    reviewed_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    resolution: Mapped[str | None] = mapped_column(Text)

    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id])
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])
