"""Administrator analytics, account moderation, and user reports."""

from datetime import timedelta
from uuid import UUID

from flask import Blueprint, abort, request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from backend.app.api.v1.common import authenticated, json_response, load_json, roles_required
from backend.app.api.v1.schemas import (
    ReportReviewSchema,
    ReportWriteSchema,
    UserRoleUpdateSchema,
    UserStatusUpdateSchema,
)
from backend.app.api.v1.serializers import serialize_admin_user, serialize_post
from backend.app.core.extensions import db, limiter
from backend.app.models.activity import PostAnalyticsEvent, Report
from backend.app.models.enums import (
    AnalyticsEventType,
    PostStatus,
    ReportStatus,
    ReportTargetType,
    UserRole,
)
from backend.app.models.interaction import Comment, Like
from backend.app.models.mixins import utcnow
from backend.app.models.post import Post
from backend.app.models.user import User

admin_api = Blueprint("admin", __name__)
reports_api = Blueprint("reports", __name__)


def _page_values() -> tuple[int, int]:
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        abort(400, description="page and per_page must be integers.")
    if page < 1 or per_page < 1 or per_page > 100:
        abort(400, description="page must be positive and per_page must be between 1 and 100.")
    return page, per_page


def _pagination(pagination, items):
    return {
        "items": items,
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    }


def _target_exists(target_type: ReportTargetType, target_id: UUID) -> bool:
    if target_type == ReportTargetType.USER:
        return db.session.get(User, target_id) is not None
    if target_type == ReportTargetType.POST:
        return db.session.get(Post, target_id) is not None
    return db.session.get(Comment, target_id) is not None


@reports_api.post("")
@authenticated
@limiter.limit("10 per hour")
def create_report(user: User):
    data = load_json(ReportWriteSchema())
    target_type = ReportTargetType(data["target_type"])
    target_id = data["target_id"]
    if not _target_exists(target_type, target_id):
        abort(404, description="The report target was not found.")
    if target_type == ReportTargetType.USER and target_id == user.id:
        abort(400, description="You cannot report your own account.")
    existing = db.session.scalar(
        select(Report.id).where(
            Report.reporter_id == user.id,
            Report.target_type == target_type,
            Report.target_id == target_id,
            Report.status == ReportStatus.PENDING,
        )
    )
    if existing is not None:
        abort(409, description="You already have a pending report for this item.")
    report = Report(
        reporter_id=user.id,
        target_type=target_type,
        target_id=target_id,
        reason=data["reason"].strip(),
        details=data.get("details"),
    )
    if not report.reason:
        abort(400, description="reason must not be blank.")
    db.session.add(report)
    db.session.commit()
    return json_response({"id": str(report.id), "status": report.status.value}, 201)


@admin_api.get("/users")
@roles_required(UserRole.ADMIN)
def list_users(_admin):
    page, per_page = _page_values()
    statement = select(User).order_by(User.created_at.desc())
    search = request.args.get("q", "").strip()
    if search:
        if len(search) > 200:
            abort(400, description="Search queries may not exceed 200 characters.")
        escaped = search.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped}%"
        statement = statement.where(
            or_(
                User.username.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
            )
        )
    pagination = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    return json_response(
        _pagination(pagination, [serialize_admin_user(user) for user in pagination.items])
    )


@admin_api.patch("/users/<uuid:user_id>/role")
@roles_required(UserRole.ADMIN)
def update_user_role(admin: User, user_id: UUID):
    target = db.session.get(User, user_id)
    if target is None or target.deleted_at is not None:
        abort(404, description="The requested user was not found.")
    data = load_json(UserRoleUpdateSchema())
    role = UserRole(data["role"])
    if target.id == admin.id and role != UserRole.ADMIN:
        abort(400, description="You cannot remove your own administrator role.")
    if target.role == UserRole.ADMIN and role != UserRole.ADMIN:
        active_admins = db.session.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        if (active_admins or 0) <= 1:
            abort(409, description="The last active administrator cannot be demoted.")
    target.role = role
    target.auth_token_version += 1
    db.session.commit()
    return json_response(serialize_admin_user(target))


@admin_api.patch("/users/<uuid:user_id>/status")
@roles_required(UserRole.ADMIN)
def update_user_status(admin: User, user_id: UUID):
    target = db.session.get(User, user_id)
    if target is None or target.deleted_at is not None:
        abort(404, description="The requested user was not found.")
    data = load_json(UserStatusUpdateSchema())
    if target.id == admin.id and not data["is_active"]:
        abort(400, description="You cannot deactivate your own account.")
    if target.role == UserRole.ADMIN and not data["is_active"]:
        active_admins = db.session.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        if (active_admins or 0) <= 1:
            abort(409, description="The last active administrator cannot be deactivated.")
    target.is_active = data["is_active"]
    target.auth_token_version += 1
    db.session.commit()
    return json_response(serialize_admin_user(target))


@admin_api.get("/posts")
@roles_required(UserRole.ADMIN)
def list_all_posts(_admin):
    page, per_page = _page_values()
    statement = (
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.categories), selectinload(Post.tags))
        .order_by(Post.created_at.desc())
    )
    status = request.args.get("status")
    if status:
        try:
            statement = statement.where(Post.status == PostStatus(status))
        except ValueError:
            abort(400, description="Unsupported post status.")
    pagination = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    return json_response(
        _pagination(
            pagination,
            [serialize_post(post, include_content=False) for post in pagination.items],
        )
    )


@admin_api.get("/reports")
@roles_required(UserRole.ADMIN)
def list_reports(_admin):
    page, per_page = _page_values()
    statement = select(Report).order_by(Report.created_at.desc())
    status = request.args.get("status", "pending")
    try:
        report_status = ReportStatus(status)
    except ValueError:
        abort(400, description="Unsupported report status.")
    statement = statement.where(Report.status == report_status)
    pagination = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    items = [
        {
            "id": str(report.id),
            "reporter_id": str(report.reporter_id),
            "target_type": report.target_type.value,
            "target_id": str(report.target_id),
            "reason": report.reason,
            "details": report.details,
            "status": report.status.value,
            "resolution": report.resolution,
            "created_at": report.created_at.isoformat(),
        }
        for report in pagination.items
    ]
    return json_response(_pagination(pagination, items))


@admin_api.patch("/reports/<uuid:report_id>")
@roles_required(UserRole.ADMIN)
def review_report(admin: User, report_id: UUID):
    report = db.session.get(Report, report_id)
    if report is None:
        abort(404, description="The requested report was not found.")
    data = load_json(ReportReviewSchema())
    report.status = ReportStatus(data["status"])
    report.resolution = data.get("resolution")
    report.reviewed_by_id = admin.id
    db.session.commit()
    return json_response(
        {
            "id": str(report.id),
            "status": report.status.value,
            "resolution": report.resolution,
            "reviewed_by_id": str(report.reviewed_by_id),
        }
    )


@admin_api.get("/analytics")
@roles_required(UserRole.ADMIN)
def analytics_overview(_admin):
    try:
        days = int(request.args.get("days", "30"))
    except ValueError:
        abort(400, description="days must be an integer.")
    if days < 1 or days > 365:
        abort(400, description="days must be between 1 and 365.")

    since = utcnow() - timedelta(days=days)
    like_count = (
        select(func.count(Like.id))
        .where(Like.post_id == Post.id)
        .correlate(Post)
        .scalar_subquery()
    )
    popular_posts = db.session.scalars(
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.categories), selectinload(Post.tags))
        .where(Post.status == PostStatus.PUBLISHED)
        .order_by(like_count.desc(), Post.published_at.desc())
        .limit(10)
    ).all()
    event_counts = {
        event_type.value: db.session.scalar(
            select(func.count(PostAnalyticsEvent.id)).where(
                PostAnalyticsEvent.event_type == event_type,
                PostAnalyticsEvent.created_at >= since,
            )
        )
        or 0
        for event_type in AnalyticsEventType
    }
    return json_response(
        {
            "period_days": days,
            "users": {
                "total": db.session.scalar(select(func.count(User.id))) or 0,
                "active": db.session.scalar(
                    select(func.count(User.id)).where(
                        User.is_active.is_(True),
                        User.deleted_at.is_(None),
                    )
                )
                or 0,
            },
            "posts": {
                "total": db.session.scalar(select(func.count(Post.id))) or 0,
                "published": db.session.scalar(
                    select(func.count(Post.id)).where(Post.status == PostStatus.PUBLISHED)
                )
                or 0,
                "drafts": db.session.scalar(
                    select(func.count(Post.id)).where(Post.status == PostStatus.DRAFT)
                )
                or 0,
            },
            "comments": db.session.scalar(select(func.count(Comment.id))) or 0,
            "reports_pending": db.session.scalar(
                select(func.count(Report.id)).where(Report.status == ReportStatus.PENDING)
            )
            or 0,
            "events": event_counts,
            "popular_posts": [
                serialize_post(post, include_content=False) for post in popular_posts
            ],
        }
    )
