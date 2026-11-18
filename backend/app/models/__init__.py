"""Import all models so SQLAlchemy and Alembic discover their tables."""

from backend.app.models.activity import PostAnalyticsEvent, Report
from backend.app.models.enums import (
    AnalyticsEventType,
    NotificationType,
    PostStatus,
    ReportStatus,
    ReportTargetType,
    UserRole,
)
from backend.app.models.interaction import (
    Bookmark,
    Comment,
    Follow,
    Like,
    Notification,
)
from backend.app.models.post import Post
from backend.app.models.security import TokenRevocation
from backend.app.models.taxonomy import Category, Tag
from backend.app.models.user import User

__all__ = [
    "AnalyticsEventType",
    "Bookmark",
    "Category",
    "Comment",
    "Follow",
    "Like",
    "Notification",
    "NotificationType",
    "Post",
    "PostAnalyticsEvent",
    "PostStatus",
    "Report",
    "ReportStatus",
    "ReportTargetType",
    "Tag",
    "TokenRevocation",
    "User",
    "UserRole",
]
