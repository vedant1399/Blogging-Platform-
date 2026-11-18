"""Enumerations persisted by the blogging platform."""

from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    AUTHOR = "author"
    ADMIN = "admin"


class PostStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class NotificationType(str, Enum):
    NEW_FOLLOWER = "new_follower"
    NEW_COMMENT = "new_comment"
    COMMENT_REPLY = "comment_reply"
    POST_LIKE = "post_like"
    COMMENT_LIKE = "comment_like"
    PUBLISHED_POST = "published_post"


class AnalyticsEventType(str, Enum):
    VIEW = "view"
    READ = "read"
    SHARE = "share"


class ReportTargetType(str, Enum):
    USER = "user"
    POST = "post"
    COMMENT = "comment"


class ReportStatus(str, Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
