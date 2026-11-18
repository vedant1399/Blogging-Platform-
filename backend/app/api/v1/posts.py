"""Post discovery, publishing, authoring, and analytics endpoints."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bleach
from flask import Blueprint, abort, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from slugify import slugify

from backend.app.api.v1.common import (
    authenticated,
    json_response,
    load_json,
    roles_required,
)
from backend.app.api.v1.schemas import PostReadSchema, PostWriteSchema
from backend.app.api.v1.serializers import serialize_post
from backend.app.core.extensions import db, limiter
from backend.app.models.enums import (
    AnalyticsEventType,
    NotificationType,
    PostStatus,
    UserRole,
)
from backend.app.models.interaction import Comment, Like, Notification
from backend.app.models.mixins import utcnow
from backend.app.models.post import Post
from backend.app.models.taxonomy import Category, Tag
from backend.app.models.user import User
from backend.app.models.activity import PostAnalyticsEvent

posts_api = Blueprint("posts", __name__)

ALLOWED_CONTENT_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "hr",
    "pre",
    "code",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "video",
    "source",
}
ALLOWED_CONTENT_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "video": ["controls", "width", "height", "poster"],
    "source": ["src", "type"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
}


def _pagination_values() -> tuple[int, int]:
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        abort(400, description="page and per_page must be integers.")
    if page < 1 or per_page < 1 or per_page > 100:
        abort(400, description="page must be positive and per_page must be between 1 and 100.")
    return page, per_page


def _pagination_response(pagination, items: list[dict]):
    return json_response(
        {
            "items": items,
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }
    )


def _sanitize_content(value: str) -> str:
    return bleach.clean(
        value,
        tags=ALLOWED_CONTENT_TAGS,
        attributes=ALLOWED_CONTENT_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )


def _read_time_minutes(content: str) -> int:
    plain_text = html.unescape(re.sub(r"<[^>]*>", " ", content))
    words = len(re.findall(r"\b[\w'-]+\b", plain_text))
    return max(1, (words + 199) // 200)


def _unique_slug(title: str, requested_slug: str | None, *, exclude_id=None) -> str:
    base_slug = slugify(requested_slug or title, max_length=230) or "post"
    candidate = base_slug
    suffix = 2
    while True:
        statement = select(Post.id).where(Post.slug == candidate)
        if exclude_id is not None:
            statement = statement.where(Post.id != exclude_id)
        if db.session.scalar(statement) is None:
            return candidate
        candidate = f"{base_slug[:245]}-{suffix}"
        suffix += 1


def _assign_taxonomy(post: Post, data: dict) -> None:
    if "category_ids" in data:
        ids = set(data["category_ids"])
        categories = list(db.session.scalars(select(Category).where(Category.id.in_(ids))))
        if len(categories) != len(ids):
            abort(400, description="One or more categories do not exist.")
        post.categories = categories
    if "tag_ids" in data:
        ids = set(data["tag_ids"])
        tags = list(db.session.scalars(select(Tag).where(Tag.id.in_(ids))))
        if len(tags) != len(ids):
            abort(400, description="One or more tags do not exist.")
        post.tags = tags


def _apply_post_data(post: Post, data: dict, *, creating: bool = False) -> None:
    if creating and ("title" not in data or "content_html" not in data):
        abort(400, description="title and content_html are required.")
    if "title" in data:
        post.title = data["title"].strip()
        if not post.title:
            abort(400, description="title must not be empty.")
    if "slug" in data or creating or (not creating and "title" in data):
        post.slug = _unique_slug(
            post.title,
            data.get("slug"),
            exclude_id=None if creating else post.id,
        )
    if "content_html" in data:
        post.content_html = _sanitize_content(data["content_html"])
    if "content_json" in data:
        post.content_json = data["content_json"]

    for field in (
        "excerpt",
        "cover_image_url",
        "meta_description",
        "seo_keywords",
        "canonical_url",
        "allow_comments",
    ):
        if field in data:
            setattr(post, field, data[field])

    if "content_html" in data:
        post.read_time_minutes = _read_time_minutes(post.content_html)
    if "category_ids" in data or "tag_ids" in data:
        _assign_taxonomy(post, data)

    if "status" in data:
        try:
            status = PostStatus(data["status"])
        except ValueError:
            abort(400, description="Unsupported post status.")
        if status == PostStatus.SCHEDULED:
            scheduled_at = data.get("scheduled_at", post.scheduled_at)
            if scheduled_at is None:
                abort(400, description="scheduled_at is required for scheduled posts.")
            if scheduled_at.tzinfo is None:
                abort(400, description="scheduled_at must include a timezone.")
            scheduled_at = scheduled_at.astimezone(UTC)
            if scheduled_at <= utcnow():
                abort(400, description="scheduled_at must be in the future.")
            if not html.unescape(re.sub(r"<[^>]*>", "", post.content_html)).strip():
                abort(400, description="A post needs content before it can be scheduled.")
            post.scheduled_at = scheduled_at
            post.published_at = None
            post.archived_at = None
        elif status == PostStatus.PUBLISHED:
            if not html.unescape(re.sub(r"<[^>]*>", "", post.content_html)).strip():
                abort(400, description="A post needs content before it can be published.")
            post.published_at = post.published_at or utcnow()
            post.scheduled_at = None
            post.archived_at = None
        elif status == PostStatus.ARCHIVED:
            post.archived_at = utcnow()
            post.scheduled_at = None
        else:
            post.scheduled_at = None
            post.archived_at = None
        post.status = status
    elif creating:
        post.status = PostStatus.DRAFT


def _can_manage(post: Post, user: User) -> bool:
    return post.author_id == user.id or user.role == UserRole.ADMIN


def _post_or_404(slug: str) -> Post:
    post = db.session.scalar(
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.categories), selectinload(Post.tags))
        .where(Post.slug == slug)
    )
    if post is None:
        abort(404, description="The requested post was not found.")
    return post


@posts_api.get("")
@limiter.limit("120 per minute")
def list_posts():
    page, per_page = _pagination_values()
    statement = (
        select(Post)
        .join(Post.author)
        .options(selectinload(Post.author), selectinload(Post.categories), selectinload(Post.tags))
        .where(
            Post.status == PostStatus.PUBLISHED,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )

    search = request.args.get("q", "").strip()
    if search:
        if len(search) > 200:
            abort(400, description="Search queries may not exceed 200 characters.")
        escaped = search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped}%"
        statement = statement.where(
            or_(
                Post.title.ilike(pattern, escape="\\"),
                Post.excerpt.ilike(pattern, escape="\\"),
                Post.content_html.ilike(pattern, escape="\\"),
                User.username.ilike(pattern, escape="\\"),
                Post.categories.any(Category.name.ilike(pattern, escape="\\")),
                Post.tags.any(Tag.name.ilike(pattern, escape="\\")),
            )
        )

    category_slug = request.args.get("category")
    if category_slug:
        statement = statement.where(Post.categories.any(Category.slug == category_slug))
    tag_slug = request.args.get("tag")
    if tag_slug:
        statement = statement.where(Post.tags.any(Tag.slug == tag_slug))
    author_name = request.args.get("author")
    if author_name:
        statement = statement.where(func.lower(User.username) == author_name.lower())
    for parameter, comparison in (
        ("published_after", lambda value: Post.published_at >= value),
        ("published_before", lambda value: Post.published_at <= value),
    ):
        raw_value = request.args.get(parameter)
        if raw_value:
            try:
                date_value = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
            except ValueError:
                abort(400, description=f"{parameter} must be an ISO-8601 datetime.")
            if date_value.tzinfo is None:
                abort(400, description=f"{parameter} must include a timezone.")
            statement = statement.where(comparison(date_value.astimezone(UTC)))

    sort = request.args.get("sort", "latest")
    like_count = (
        select(func.count(Like.id))
        .where(Like.post_id == Post.id)
        .correlate(Post)
        .scalar_subquery()
    )
    comment_count = (
        select(func.count(Comment.id))
        .where(Comment.post_id == Post.id, Comment.deleted_at.is_(None))
        .correlate(Post)
        .scalar_subquery()
    )
    if sort == "oldest":
        statement = statement.order_by(Post.published_at.asc(), Post.id)
    elif sort in {"popular", "most_liked"}:
        statement = statement.order_by(like_count.desc(), Post.published_at.desc())
    elif sort == "most_commented":
        statement = statement.order_by(comment_count.desc(), Post.published_at.desc())
    elif sort == "trending":
        recent_activity = (
            select(func.count(PostAnalyticsEvent.id))
            .where(
                PostAnalyticsEvent.post_id == Post.id,
                PostAnalyticsEvent.created_at >= utcnow() - timedelta(days=7),
                PostAnalyticsEvent.event_type.in_(
                    [AnalyticsEventType.VIEW, AnalyticsEventType.READ]
                ),
            )
            .correlate(Post)
            .scalar_subquery()
        )
        statement = statement.order_by(recent_activity.desc(), Post.published_at.desc())
    elif sort == "latest":
        statement = statement.order_by(Post.published_at.desc(), Post.id)
    else:
        abort(400, description="sort must be latest, oldest, trending, popular, most_liked, or most_commented.")

    pagination = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    return _pagination_response(
        pagination,
        [serialize_post(post, include_content=False) for post in pagination.items],
    )


@posts_api.get("/suggestions")
@limiter.limit("60 per minute")
def suggest_posts():
    query = request.args.get("q", "").strip()
    if len(query) < 2 or len(query) > 100:
        abort(400, description="q must contain between 2 and 100 characters.")
    escaped = query.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    items = db.session.execute(
        select(Post.title, Post.slug)
        .join(Post.author)
        .where(
            Post.status == PostStatus.PUBLISHED,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            Post.title.ilike(f"%{escaped}%", escape="\\"),
        )
        .order_by(Post.published_at.desc())
        .limit(8)
    ).all()
    return json_response(
        {"items": [{"title": title, "slug": slug} for title, slug in items]}
    )


@posts_api.get("/<slug>")
@jwt_required(optional=True)
@limiter.limit("120 per minute")
def get_post(slug: str):
    post = _post_or_404(slug)
    identity = get_jwt_identity()
    viewer = None
    if identity:
        try:
            viewer = db.session.get(User, UUID(identity))
        except (TypeError, ValueError):
            viewer = None
    if (
        viewer is not None
        and (
            not viewer.is_active
            or viewer.deleted_at is not None
            or get_jwt().get("auth_version") != viewer.auth_token_version
        )
    ):
        viewer = None
    if post.status != PostStatus.PUBLISHED:
        if viewer is None or not _can_manage(post, viewer):
            abort(404, description="The requested post was not found.")

    db.session.add(
        PostAnalyticsEvent(
            post_id=post.id,
            actor_id=viewer.id if viewer else None,
            event_type=AnalyticsEventType.VIEW,
        )
    )
    db.session.commit()
    return json_response(serialize_post(post, viewer_id=viewer.id if viewer else None))


@posts_api.post("")
@roles_required(UserRole.AUTHOR, UserRole.ADMIN)
@limiter.limit("30 per hour")
def create_post(user: User):
    if not user.is_email_verified:
        abort(403, description="Verify your email before publishing.")
    data = load_json(PostWriteSchema())
    post = Post(author=user, title="", slug="", content_html="")
    with db.session.no_autoflush:
        _apply_post_data(post, data, creating=True)
    db.session.add(post)
    db.session.commit()
    return json_response(serialize_post(post, viewer_id=user.id), 201)


@posts_api.patch("/<slug>")
@authenticated
def update_post(user: User, slug: str):
    post = _post_or_404(slug)
    if not _can_manage(post, user):
        abort(403, description="You may only edit your own posts.")
    data = load_json(PostWriteSchema())
    _apply_post_data(post, data)
    db.session.commit()
    return json_response(serialize_post(post, viewer_id=user.id))


@posts_api.delete("/<slug>")
@authenticated
def delete_post(user: User, slug: str):
    post = _post_or_404(slug)
    if not _can_manage(post, user):
        abort(403, description="You may only delete your own posts.")
    db.session.delete(post)
    db.session.commit()
    return "", 204


@posts_api.post("/<slug>/publish")
@authenticated
def publish_post(user: User, slug: str):
    post = _post_or_404(slug)
    if not _can_manage(post, user):
        abort(403, description="You may only publish your own posts.")
    if not html.unescape(re.sub(r"<[^>]*>", "", post.content_html)).strip():
        abort(400, description="A post needs content before it can be published.")
    post.status = PostStatus.PUBLISHED
    post.published_at = post.published_at or utcnow()
    post.scheduled_at = None
    post.archived_at = None
    db.session.commit()
    return json_response(serialize_post(post, viewer_id=user.id))


@posts_api.post("/<slug>/archive")
@authenticated
def archive_post(user: User, slug: str):
    post = _post_or_404(slug)
    if not _can_manage(post, user):
        abort(403, description="You may only archive your own posts.")
    post.status = PostStatus.ARCHIVED
    post.archived_at = utcnow()
    post.scheduled_at = None
    db.session.commit()
    return json_response(serialize_post(post, viewer_id=user.id))


@posts_api.get("/<slug>/preview")
@authenticated
def preview_post(user: User, slug: str):
    post = _post_or_404(slug)
    if not _can_manage(post, user):
        abort(404, description="The requested post was not found.")
    return json_response(serialize_post(post, viewer_id=user.id))


@posts_api.post("/<slug>/duplicate")
@authenticated
def duplicate_post(user: User, slug: str):
    source = _post_or_404(slug)
    if not _can_manage(source, user):
        abort(404, description="The requested post was not found.")
    duplicate = Post(
        author=user,
        title=f"{source.title} (copy)",
        slug=_unique_slug(f"{source.title} copy", None),
        excerpt=source.excerpt,
        content_html=source.content_html,
        content_json=source.content_json,
        cover_image_url=source.cover_image_url,
        meta_description=source.meta_description,
        seo_keywords=list(source.seo_keywords),
        canonical_url=None,
        status=PostStatus.DRAFT,
        read_time_minutes=source.read_time_minutes,
        allow_comments=source.allow_comments,
        categories=list(source.categories),
        tags=list(source.tags),
    )
    db.session.add(duplicate)
    db.session.commit()
    return json_response(serialize_post(duplicate, viewer_id=user.id), 201)


@posts_api.post("/<slug>/share")
@limiter.limit("30 per minute")
def record_share(slug: str):
    post = db.session.scalar(
        select(Post).where(Post.slug == slug, Post.status == PostStatus.PUBLISHED)
    )
    if post is None:
        abort(404, description="The requested post was not found.")
    db.session.add(
        PostAnalyticsEvent(
            post_id=post.id,
            event_type=AnalyticsEventType.SHARE,
        )
    )
    db.session.commit()
    return json_response({"message": "Share recorded."}, 202)


@posts_api.post("/<slug>/read")
@jwt_required(optional=True)
@limiter.limit("30 per minute")
def record_read(slug: str):
    data = load_json(PostReadSchema())
    post = db.session.scalar(
        select(Post).where(Post.slug == slug, Post.status == PostStatus.PUBLISHED)
    )
    if post is None:
        abort(404, description="The requested post was not found.")
    identity = get_jwt_identity()
    actor_id = None
    if identity:
        try:
            actor_id = UUID(identity)
        except (TypeError, ValueError):
            actor_id = None
    db.session.add(
        PostAnalyticsEvent(
            post_id=post.id,
            actor_id=actor_id,
            event_type=AnalyticsEventType.READ,
            reading_time_seconds=data["reading_time_seconds"],
        )
    )
    db.session.commit()
    return json_response({"message": "Read recorded."}, 202)
