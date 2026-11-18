"""Public category/tag browsing and administrator management endpoints."""

from flask import Blueprint, abort, request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from slugify import slugify

from backend.app.api.v1.common import json_response, load_json, roles_required
from backend.app.api.v1.schemas import CategoryWriteSchema, TagWriteSchema
from backend.app.api.v1.serializers import serialize_category, serialize_post, serialize_tag
from backend.app.core.extensions import db
from backend.app.models.enums import PostStatus, UserRole
from backend.app.models.post import Post
from backend.app.models.taxonomy import Category, Tag

taxonomy_api = Blueprint("taxonomy", __name__)


def _page_values() -> tuple[int, int]:
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        abort(400, description="page and per_page must be integers.")
    if page < 1 or per_page < 1 or per_page > 100:
        abort(400, description="page must be positive and per_page must be between 1 and 100.")
    return page, per_page


def _taxonomy_posts(statement):
    page, per_page = _page_values()
    statement = (
        statement.where(Post.status == PostStatus.PUBLISHED)
        .options(selectinload(Post.author), selectinload(Post.categories), selectinload(Post.tags))
        .order_by(Post.published_at.desc(), Post.id)
    )
    pagination = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    return {
        "items": [serialize_post(post, include_content=False) for post in pagination.items],
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        },
    }


@taxonomy_api.get("/categories")
def list_categories():
    page, per_page = _page_values()
    statement = select(Category).order_by(func.lower(Category.name))
    pagination = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    items = []
    for category in pagination.items:
        post_count = db.session.scalar(
            select(func.count(Post.id)).where(
                Post.categories.any(Category.id == category.id),
                Post.status == PostStatus.PUBLISHED,
            )
        )
        items.append({**serialize_category(category), "published_posts": post_count or 0})
    return json_response(
        {
            "items": items,
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
            },
        }
    )


@taxonomy_api.get("/categories/<slug>")
def get_category(slug: str):
    category = db.session.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        abort(404, description="The requested category was not found.")
    return json_response(
        {
            **serialize_category(category),
            "posts": _taxonomy_posts(select(Post).where(Post.categories.any(Category.id == category.id))),
        }
    )


@taxonomy_api.post("/categories")
@roles_required(UserRole.ADMIN)
def create_category(user):
    data = load_json(CategoryWriteSchema())
    if not data.get("name"):
        abort(400, description="name is required.")
    name = data["name"].strip()
    if not name:
        abort(400, description="name must not be blank.")
    slug = slugify(data.get("slug") or name, max_length=100)
    category = Category(name=name, slug=slug, description=data.get("description"))
    category.created_by_id = user.id
    db.session.add(category)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="A category with that name or slug already exists.")
    return json_response(serialize_category(category), 201)


@taxonomy_api.patch("/categories/<slug>")
@roles_required(UserRole.ADMIN)
def update_category(_user, slug: str):
    category = db.session.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        abort(404, description="The requested category was not found.")
    data = load_json(CategoryWriteSchema())
    if not data:
        abort(400, description="Provide at least one category field to update.")
    if "name" in data:
        category.name = data["name"].strip()
        if not category.name:
            abort(400, description="name must not be blank.")
    if "slug" in data or "name" in data:
        category.slug = slugify(data.get("slug") or category.name, max_length=100)
    if "description" in data:
        category.description = data["description"]
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="A category with that name or slug already exists.")
    return json_response(serialize_category(category))


@taxonomy_api.delete("/categories/<slug>")
@roles_required(UserRole.ADMIN)
def delete_category(_user, slug: str):
    category = db.session.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        abort(404, description="The requested category was not found.")
    db.session.delete(category)
    db.session.commit()
    return "", 204


@taxonomy_api.get("/tags")
def list_tags():
    page, per_page = _page_values()
    pagination = db.paginate(
        select(Tag).order_by(func.lower(Tag.name)),
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return json_response(
        {
            "items": [serialize_tag(tag) for tag in pagination.items],
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
            },
        }
    )


@taxonomy_api.get("/tags/<slug>")
def get_tag(slug: str):
    tag = db.session.scalar(select(Tag).where(Tag.slug == slug))
    if tag is None:
        abort(404, description="The requested tag was not found.")
    return json_response(
        {
            **serialize_tag(tag),
            "posts": _taxonomy_posts(select(Post).where(Post.tags.any(Tag.id == tag.id))),
        }
    )


@taxonomy_api.post("/tags")
@roles_required(UserRole.ADMIN)
def create_tag(_user):
    data = load_json(TagWriteSchema())
    if not data.get("name"):
        abort(400, description="name is required.")
    name = data["name"].strip()
    if not name:
        abort(400, description="name must not be blank.")
    tag = Tag(name=name, slug=slugify(data.get("slug") or name, max_length=80))
    db.session.add(tag)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="A tag with that name or slug already exists.")
    return json_response(serialize_tag(tag), 201)


@taxonomy_api.patch("/tags/<slug>")
@roles_required(UserRole.ADMIN)
def update_tag(_user, slug: str):
    tag = db.session.scalar(select(Tag).where(Tag.slug == slug))
    if tag is None:
        abort(404, description="The requested tag was not found.")
    data = load_json(TagWriteSchema())
    if not data:
        abort(400, description="Provide at least one tag field to update.")
    if "name" in data:
        tag.name = data["name"].strip()
        if not tag.name:
            abort(400, description="name must not be blank.")
    if "slug" in data or "name" in data:
        tag.slug = slugify(data.get("slug") or tag.name, max_length=80)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="A tag with that name or slug already exists.")
    return json_response(serialize_tag(tag))


@taxonomy_api.delete("/tags/<slug>")
@roles_required(UserRole.ADMIN)
def delete_tag(_user, slug: str):
    tag = db.session.scalar(select(Tag).where(Tag.slug == slug))
    if tag is None:
        abort(404, description="The requested tag was not found.")
    db.session.delete(tag)
    db.session.commit()
    return "", 204
