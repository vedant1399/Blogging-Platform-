"""Post categories and tags."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.extensions import db
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from backend.app.models.post import post_categories, post_tags

if TYPE_CHECKING:
    from backend.app.models.post import Post


class Category(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    posts: Mapped[list[Post]] = relationship(
        secondary=post_categories,
        back_populates="categories",
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} slug={self.slug!r}>"


class Tag(UUIDPrimaryKeyMixin, TimestampMixin, db.Model):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(60), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)

    posts: Mapped[list[Post]] = relationship(
        secondary=post_tags,
        back_populates="tags",
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} slug={self.slug!r}>"


Index("uq_categories_name_ci", func.lower(Category.name), unique=True)
Index("uq_tags_name_ci", func.lower(Tag.name), unique=True)
