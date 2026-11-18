"""Blog posts and their many-to-many taxonomy associations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.extensions import db
from backend.app.models.enums import PostStatus
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.models.interaction import Bookmark, Comment, Like, Notification
    from backend.app.models.taxonomy import Category, Tag
    from backend.app.models.user import User


post_categories = Table(
    "post_categories",
    db.metadata,
    Column(
        "post_id",
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        Uuid(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

post_tags = Table(
    "post_tags",
    db.metadata,
    Column(
        "post_id",
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Uuid(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Post(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint("read_time_minutes >= 1", name="read_time_positive"),
        Index("ix_posts_status_published_at", "status", "published_at"),
        Index("ix_posts_author_status", "author_id", "status"),
    )

    author_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(260), nullable=False, unique=True)
    excerpt: Mapped[str | None] = mapped_column(String(500))
    content_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    cover_image_url: Mapped[str | None] = mapped_column(String(2048))
    meta_description: Mapped[str | None] = mapped_column(String(320))
    seo_keywords: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[PostStatus] = mapped_column(
        Enum(
            PostStatus,
            name="post_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [member.value for member in enum_type],
        ),
        nullable=False,
        default=PostStatus.DRAFT,
        index=True,
    )
    read_time_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    allow_comments: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User] = relationship(back_populates="posts")
    categories: Mapped[list[Category]] = relationship(
        secondary=post_categories,
        back_populates="posts",
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary=post_tags,
        back_populates="posts",
    )
    comments: Mapped[list[Comment]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    likes: Mapped[list[Like]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    bookmarks: Mapped[list[Bookmark]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    notifications: Mapped[list[Notification]] = relationship(back_populates="post")

    def __repr__(self) -> str:
        return f"<Post id={self.id} slug={self.slug!r} status={self.status.value!r}>"
