"""Nested comments and ownership-checked moderation endpoints."""

import bleach
from flask import Blueprint, abort, request
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID

from backend.app.api.v1.common import authenticated, json_response, load_json
from backend.app.api.v1.schemas import CommentWriteSchema
from backend.app.api.v1.serializers import serialize_comment
from backend.app.core.extensions import db, limiter
from backend.app.models.enums import NotificationType, PostStatus, UserRole
from backend.app.models.interaction import Comment, Notification
from backend.app.models.mixins import utcnow
from backend.app.models.post import Post
from backend.app.models.user import User

comments_api = Blueprint("comments", __name__)


def _pagination_values() -> tuple[int, int]:
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        abort(400, description="page and per_page must be integers.")
    if page < 1 or per_page < 1 or per_page > 100:
        abort(400, description="page must be positive and per_page must be between 1 and 100.")
    return page, per_page


def _published_post(slug: str) -> Post:
    post = db.session.scalar(
        select(Post).where(
            Post.slug == slug,
            Post.status == PostStatus.PUBLISHED,
        )
    )
    if post is None:
        abort(404, description="The requested post was not found.")
    return post


def _comment_or_404(comment_id: UUID) -> Comment:
    comment = db.session.scalar(
        select(Comment)
        .options(selectinload(Comment.author), selectinload(Comment.replies))
        .where(Comment.id == comment_id)
    )
    if comment is None:
        abort(404, description="The requested comment was not found.")
    return comment


def _plain_comment_body(body: str) -> str:
    plain_text = bleach.clean(body, tags=[], attributes={}, strip=True).strip()
    if not plain_text:
        abort(400, description="Comment text must not be empty.")
    return plain_text


def _comment_depth(comment: Comment) -> int:
    depth = 1
    parent = comment.parent
    while parent is not None:
        depth += 1
        if depth > 8:
            abort(400, description="Comment replies may not exceed eight levels.")
        parent = parent.parent
    return depth


@comments_api.get("/posts/<slug>/comments")
@limiter.limit("120 per minute")
def list_post_comments(slug: str):
    post = _published_post(slug)
    page, per_page = _pagination_values()
    statement = (
        select(Comment)
        .options(selectinload(Comment.author), selectinload(Comment.replies))
        .where(
            Comment.post_id == post.id,
            Comment.parent_id.is_(None),
        )
        .order_by(Comment.created_at.asc(), Comment.id)
    )
    pagination = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    visible_comments = [
        comment
        for comment in pagination.items
        if comment.deleted_at is None or comment.replies
    ]
    return json_response(
        {
            "items": [serialize_comment(comment) for comment in visible_comments],
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
            },
        }
    )


@comments_api.post("/posts/<slug>/comments")
@authenticated
@limiter.limit("30 per hour")
def create_comment(user: User, slug: str):
    post = _published_post(slug)
    if not post.allow_comments:
        abort(403, description="Comments are disabled for this post.")
    data = load_json(CommentWriteSchema())
    parent = None
    if data.get("parent_id") is not None:
        parent = _comment_or_404(data["parent_id"])
        if parent.post_id != post.id or parent.deleted_at is not None:
            abort(400, description="Replies must target an active comment on this post.")
        if _comment_depth(parent) >= 8:
            abort(400, description="Comment replies may not exceed eight levels.")

    comment = Comment(
        post=post,
        author=user,
        parent=parent,
        body=_plain_comment_body(data["body"]),
    )
    db.session.add(comment)
    recipient = parent.author if parent else post.author
    if recipient.id != user.id:
        db.session.add(
            Notification(
                recipient=recipient,
                actor=user,
                type=NotificationType.COMMENT_REPLY if parent else NotificationType.NEW_COMMENT,
                post=post,
                comment=comment,
                message=(
                    f"{user.username} replied to your comment."
                    if parent
                    else f"{user.username} commented on your post."
                ),
            )
        )
    db.session.commit()
    return json_response(serialize_comment(comment), 201)


@comments_api.patch("/comments/<uuid:comment_id>")
@authenticated
def edit_comment(user: User, comment_id: UUID):
    comment = _comment_or_404(comment_id)
    if comment.deleted_at is not None:
        abort(404, description="The requested comment was not found.")
    if comment.author_id != user.id and user.role != UserRole.ADMIN:
        abort(403, description="Only the comment owner or an administrator may edit it.")
    data = load_json(CommentWriteSchema())
    if "parent_id" in data and data["parent_id"] != comment.parent_id:
        abort(400, description="A comment's parent cannot be changed.")
    comment.body = _plain_comment_body(data["body"])
    db.session.commit()
    return json_response(serialize_comment(comment))


@comments_api.delete("/comments/<uuid:comment_id>")
@authenticated
def delete_comment(user: User, comment_id: UUID):
    comment = _comment_or_404(comment_id)
    if comment.author_id != user.id and user.role != UserRole.ADMIN:
        abort(403, description="Only the comment owner or an administrator may delete it.")
    if comment.deleted_at is None:
        comment.deleted_at = utcnow()
        db.session.commit()
    return "", 204
