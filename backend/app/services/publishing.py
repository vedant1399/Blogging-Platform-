"""Scheduled post publication service."""

from datetime import UTC

from sqlalchemy import select

from backend.app.core.extensions import db
from backend.app.models.enums import NotificationType, PostStatus
from backend.app.models.interaction import Follow, Notification
from backend.app.models.mixins import utcnow
from backend.app.models.post import Post
from backend.app.models.user import User


def publish_due_posts() -> int:
    """Publish due scheduled posts and notify active followers."""
    posts = db.session.scalars(
        select(Post)
        .where(
            Post.status == PostStatus.SCHEDULED,
            Post.scheduled_at <= utcnow(),
        )
        .order_by(Post.scheduled_at, Post.id)
        .with_for_update(skip_locked=True)
    ).all()

    for post in posts:
        publish_time = post.scheduled_at
        if publish_time is not None and publish_time.tzinfo is None:
            publish_time = publish_time.replace(tzinfo=UTC)
        post.status = PostStatus.PUBLISHED
        post.published_at = publish_time or utcnow()
        post.scheduled_at = None

        follower_ids = db.session.scalars(
            select(Follow.follower_id)
            .join(User, User.id == Follow.follower_id)
            .where(
                Follow.followed_id == post.author_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        ).all()
        db.session.add_all(
            Notification(
                recipient_id=follower_id,
                actor_id=post.author_id,
                type=NotificationType.PUBLISHED_POST,
                post_id=post.id,
                message=f"{post.author.username} published a new post.",
            )
            for follower_id in follower_ids
        )

    if posts:
        db.session.commit()
    return len(posts)
