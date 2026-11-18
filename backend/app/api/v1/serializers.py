"""Stable JSON representations for API resources."""

from typing import Any

from sqlalchemy import func, select

from backend.app.core.extensions import db
from backend.app.models.interaction import Bookmark, Comment, Like
from backend.app.models.post import Post
from backend.app.models.taxonomy import Category, Tag
from backend.app.models.user import User


def serialize_category(category: Category) -> dict[str, Any]:
    return {
        "id": str(category.id),
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
    }


def serialize_tag(tag: Tag) -> dict[str, Any]:
    return {"id": str(tag.id), "name": tag.name, "slug": tag.slug}


def serialize_post(
    post: Post,
    *,
    viewer_id=None,
    include_content: bool = True,
) -> dict[str, Any]:
    like_count = db.session.scalar(
        select(func.count(Like.id)).where(Like.post_id == post.id)
    )
    comment_count = db.session.scalar(
        select(func.count(Comment.id)).where(
            Comment.post_id == post.id,
            Comment.deleted_at.is_(None),
        )
    )
    response = {
        "id": str(post.id),
        "title": post.title,
        "slug": post.slug,
        "excerpt": post.excerpt,
        "cover_image_url": post.cover_image_url,
        "meta_description": post.meta_description,
        "seo_keywords": post.seo_keywords,
        "canonical_url": post.canonical_url,
        "status": post.status.value,
        "read_time_minutes": post.read_time_minutes,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "updated_at": post.updated_at.isoformat(),
        "author": {
            "id": str(post.author.id),
            "username": post.author.username,
            "avatar_url": post.author.avatar_url,
        },
        "categories": [serialize_category(category) for category in post.categories],
        "tags": [serialize_tag(tag) for tag in post.tags],
        "likes_count": like_count or 0,
        "comments_count": comment_count or 0,
    }
    if include_content:
        response["content_html"] = post.content_html
        response["content_json"] = post.content_json
    if viewer_id is not None:
        response["is_liked"] = (
            db.session.scalar(
                select(Like.id).where(
                    Like.user_id == viewer_id,
                    Like.post_id == post.id,
                )
            )
            is not None
        )
        response["is_bookmarked"] = (
            db.session.scalar(
                select(Bookmark.id).where(
                    Bookmark.user_id == viewer_id,
                    Bookmark.post_id == post.id,
                )
            )
            is not None
        )
    return response


def serialize_comment(comment: Comment, *, depth: int = 0) -> dict[str, Any]:
    like_count = db.session.scalar(
        select(func.count(Like.id)).where(Like.comment_id == comment.id)
    )
    return {
        "id": str(comment.id),
        "post_id": str(comment.post_id),
        "parent_id": str(comment.parent_id) if comment.parent_id else None,
        "body": "This comment was removed." if comment.deleted_at else comment.body,
        "is_deleted": comment.deleted_at is not None,
        "created_at": comment.created_at.isoformat(),
        "updated_at": comment.updated_at.isoformat(),
        "author": {
            "id": str(comment.author.id),
            "username": comment.author.username,
            "avatar_url": comment.author.avatar_url,
        },
        "likes_count": like_count or 0,
        "replies": [
            serialize_comment(reply, depth=depth + 1)
            for reply in comment.replies
            if reply.deleted_at is None or reply.replies
        ]
        if depth < 8
        else [],
    }


def serialize_notification(notification) -> dict[str, Any]:
    return {
        "id": str(notification.id),
        "type": notification.type.value,
        "message": notification.message,
        "actor": (
            {
                "id": str(notification.actor.id),
                "username": notification.actor.username,
                "avatar_url": notification.actor.avatar_url,
            }
            if notification.actor
            else None
        ),
        "post_id": str(notification.post_id) if notification.post_id else None,
        "comment_id": str(notification.comment_id) if notification.comment_id else None,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
    }


def serialize_admin_user(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "is_active": user.is_active,
        "is_email_verified": user.is_email_verified,
        "created_at": user.created_at.isoformat(),
    }
