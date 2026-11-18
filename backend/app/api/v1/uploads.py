"""Authenticated image uploads and safe public image delivery."""

from __future__ import annotations

from flask import Blueprint, abort, current_app, request, send_from_directory
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.v1.common import authenticated, json_response
from backend.app.core.extensions import db, limiter
from backend.app.models.enums import UserRole
from backend.app.models.post import Post
from backend.app.services.image_storage import (
    InvalidImageError,
    is_managed_image_filename,
    save_uploaded_image,
)

uploads_api = Blueprint("uploads", __name__)


def _uploaded_image() -> str:
    image = request.files.get("image")
    if image is None or not image.filename:
        abort(400, description="An image file is required in the 'image' field.")

    max_bytes = current_app.config["MAX_IMAGE_UPLOAD_BYTES"]
    content = image.stream.read(max_bytes + 1)
    if len(content) > max_bytes:
        abort(413, description="The image exceeds the maximum upload size.")
    try:
        filename = save_uploaded_image(
            content,
            image.filename,
            current_app.config["UPLOAD_FOLDER"],
        )
    except InvalidImageError as error:
        abort(400, description=str(error))
    return f"/api/v1/uploads/{filename}"


@uploads_api.post("/users/me/avatar")
@limiter.limit("30 per hour")
@authenticated
def upload_avatar(user):
    user.avatar_url = _uploaded_image()
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return json_response({"avatar_url": user.avatar_url})


@uploads_api.post("/posts/<uuid:post_id>/cover")
@limiter.limit("30 per hour")
@authenticated
def upload_post_cover(user, post_id):
    post = db.session.get(Post, post_id)
    if post is None:
        abort(404, description="The requested post was not found.")
    if post.author_id != user.id and user.role != UserRole.ADMIN:
        abort(403, description="You do not have permission to edit this post.")

    post.cover_image_url = _uploaded_image()
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return json_response({"cover_image_url": post.cover_image_url})


@uploads_api.get("/uploads/<filename>")
def get_uploaded_image(filename: str):
    if not is_managed_image_filename(filename):
        abort(404)
    response = send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        filename,
        conditional=True,
        max_age=31_536_000,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
