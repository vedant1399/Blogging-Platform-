"""Likes, bookmarks, follows, and notification endpoints."""

from uuid import UUID

from flask import Blueprint, abort, request
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from backend.app.api.v1.common import authenticated, json_response
from backend.app.api.v1.serializers import serialize_notification, serialize_post
from backend.app.core.extensions import db, limiter
from backend.app.models.enums import NotificationType, PostStatus
from backend.app.models.interaction import Bookmark, Comment, Follow, Like, Notification
from backend.app.models.mixins import utcnow
from backend.app.models.post import Post
from backend.app.models.user import User

social_api = Blueprint("social", __name__)


def _page_values() -> tuple[int, int]:
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        abort(400, description="page and per_page must be integers.")
    if page < 1 or per_page < 1 or per_page > 100:
        abort(400, description="page must be positive and per_page must be between 1 and 100.")
    return page, per_page


def _public_post(slug: str) -> Post:
    post = db.session.scalar(
        select(Post).where(Post.slug == slug, Post.status == PostStatus.PUBLISHED)
    )
    if post is None:
        abort(404, description="The requested post was not found.")
    return post


def _create_notification(recipient: User, actor: User, kind: NotificationType, **target) -> None:
    if recipient.id == actor.id:
        return
    db.session.add(
        Notification(
            recipient=recipient,
            actor=actor,
            type=kind,
            message=f"{actor.username} interacted with your content.",
            **target,
        )
    )


@social_api.post("/posts/<slug>/like")
@authenticated
@limiter.limit("60 per minute")
def like_post(user: User, slug: str):
    post = _public_post(slug)
    existing = db.session.scalar(
        select(Like).where(Like.user_id == user.id, Like.post_id == post.id)
    )
    if existing is None:
        db.session.add(Like(user=user, post=post))
        _create_notification(
            post.author,
            user,
            NotificationType.POST_LIKE,
            post=post,
        )
        db.session.commit()
    return json_response({"liked": True})


@social_api.delete("/posts/<slug>/like")
@authenticated
def unlike_post(user: User, slug: str):
    post = _public_post(slug)
    like = db.session.scalar(
        select(Like).where(Like.user_id == user.id, Like.post_id == post.id)
    )
    if like is not None:
        db.session.delete(like)
        db.session.commit()
    return json_response({"liked": False})


@social_api.post("/comments/<uuid:comment_id>/like")
@authenticated
@limiter.limit("60 per minute")
def like_comment(user: User, comment_id: UUID):
    comment = db.session.scalar(
        select(Comment)
        .join(Comment.post)
        .where(
            Comment.id == comment_id,
            Comment.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
        )
    )
    if comment is None:
        abort(404, description="The requested comment was not found.")
    existing = db.session.scalar(
        select(Like).where(Like.user_id == user.id, Like.comment_id == comment.id)
    )
    if existing is None:
        db.session.add(Like(user=user, comment=comment))
        _create_notification(
            comment.author,
            user,
            NotificationType.COMMENT_LIKE,
            comment=comment,
            post=comment.post,
        )
        db.session.commit()
    return json_response({"liked": True})


@social_api.delete("/comments/<uuid:comment_id>/like")
@authenticated
def unlike_comment(user: User, comment_id: UUID):
    like = db.session.scalar(
        select(Like)
        .join(Like.comment)
        .join(Comment.post)
        .where(
            Like.user_id == user.id,
            Like.comment_id == comment_id,
            Comment.deleted_at.is_(None),
            Post.status == PostStatus.PUBLISHED,
        )
    )
    if like is not None:
        db.session.delete(like)
        db.session.commit()
    return json_response({"liked": False})


@social_api.post("/posts/<slug>/bookmark")
@authenticated
def bookmark_post(user: User, slug: str):
    post = _public_post(slug)
    existing = db.session.scalar(
        select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.post_id == post.id)
    )
    if existing is None:
        db.session.add(Bookmark(user=user, post=post))
        db.session.commit()
    return json_response({"bookmarked": True})


@social_api.delete("/posts/<slug>/bookmark")
@authenticated
def unbookmark_post(user: User, slug: str):
    post = _public_post(slug)
    bookmark = db.session.scalar(
        select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.post_id == post.id)
    )
    if bookmark is not None:
        db.session.delete(bookmark)
        db.session.commit()
    return json_response({"bookmarked": False})


@social_api.get("/users/me/bookmarks")
@authenticated
def list_bookmarks(user: User):
    page, per_page = _page_values()
    statement = (
        select(Bookmark)
        .join(Bookmark.post)
        .options(
            selectinload(Bookmark.post).selectinload(Post.author),
            selectinload(Bookmark.post).selectinload(Post.categories),
            selectinload(Bookmark.post).selectinload(Post.tags),
        )
        .where(Bookmark.user_id == user.id, Post.status == PostStatus.PUBLISHED)
        .order_by(Bookmark.created_at.desc())
    )
    pagination = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    return json_response(
        {
            "items": [
                serialize_post(bookmark.post, viewer_id=user.id)
                for bookmark in pagination.items
            ],
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
            },
        }
    )


@social_api.put("/users/<username>/follow")
@authenticated
@limiter.limit("60 per minute")
def follow_user(user: User, username: str):
    target = db.session.scalar(
        select(User).where(
            func.lower(User.username) == username.lower(),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    if target is None:
        abort(404, description="The requested profile was not found.")
    if target.id == user.id:
        abort(400, description="You cannot follow your own profile.")
    existing = db.session.scalar(
        select(Follow).where(
            Follow.follower_id == user.id,
            Follow.followed_id == target.id,
        )
    )
    if existing is None:
        db.session.add(Follow(follower=user, followed=target))
        _create_notification(target, user, NotificationType.NEW_FOLLOWER)
        db.session.commit()
    return json_response({"following": True})


@social_api.delete("/users/<username>/follow")
@authenticated
def unfollow_user(user: User, username: str):
    target = db.session.scalar(
        select(User).where(func.lower(User.username) == username.lower())
    )
    if target is None:
        abort(404, description="The requested profile was not found.")
    follow = db.session.scalar(
        select(Follow).where(
            Follow.follower_id == user.id,
            Follow.followed_id == target.id,
        )
    )
    if follow is not None:
        db.session.delete(follow)
        db.session.commit()
    return json_response({"following": False})


@social_api.get("/notifications")
@authenticated
def list_notifications(user: User):
    page, per_page = _page_values()
    statement = (
        select(Notification)
        .options(selectinload(Notification.actor))
        .where(Notification.recipient_id == user.id)
        .order_by(Notification.created_at.desc())
    )
    pagination = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    unread_count = db.session.scalar(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == user.id,
            Notification.read_at.is_(None),
        )
    )
    return json_response(
        {
            "items": [serialize_notification(item) for item in pagination.items],
            "unread_count": unread_count or 0,
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
            },
        }
    )


@social_api.patch("/notifications/<uuid:notification_id>/read")
@authenticated
def mark_notification_read(user: User, notification_id: UUID):
    notification = db.session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_id == user.id,
        )
    )
    if notification is None:
        abort(404, description="The requested notification was not found.")
    notification.read_at = notification.read_at or utcnow()
    db.session.commit()
    return json_response(serialize_notification(notification))


@social_api.post("/notifications/read-all")
@authenticated
def mark_all_notifications_read(user: User):
    now = utcnow()
    db.session.execute(
        update(Notification)
        .where(
            Notification.recipient_id == user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    db.session.commit()
    return json_response({"message": "Notifications marked as read."})
