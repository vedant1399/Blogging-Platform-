"""Profile and account-management endpoints."""

from __future__ import annotations

import secrets
from uuid import UUID

from flask import Blueprint, abort
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.api.v1.common import authenticated, json_response, load_json, user_summary
from backend.app.api.v1.schemas import PasswordConfirmationSchema, ProfileUpdateSchema
from backend.app.core.extensions import db
from backend.app.models.enums import PostStatus
from backend.app.models.interaction import Follow
from backend.app.models.mixins import utcnow
from backend.app.models.post import Post
from backend.app.models.user import User

users_api = Blueprint("users", __name__)


def _profile_counts(user_id: UUID) -> dict[str, int]:
    return {
        "published_posts": db.session.scalar(
            select(func.count(Post.id)).where(
                Post.author_id == user_id,
                Post.status == PostStatus.PUBLISHED,
            )
        )
        or 0,
        "followers": db.session.scalar(
            select(func.count(Follow.id)).where(Follow.followed_id == user_id)
        )
        or 0,
        "following": db.session.scalar(
            select(func.count(Follow.id)).where(Follow.follower_id == user_id)
        )
        or 0,
    }


def _public_profile(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "bio": user.bio,
        "avatar_url": user.avatar_url,
        "website": user.website,
        "social_links": user.social_links,
        "joined_at": user.created_at.isoformat(),
        **_profile_counts(user.id),
    }


@users_api.get("/me")
@authenticated
def get_my_profile(user: User):
    return json_response({**user_summary(user), **_public_profile(user)})


@users_api.patch("/me")
@authenticated
def update_my_profile(user: User):
    data = load_json(ProfileUpdateSchema())
    if "username" in data:
        username = data["username"].strip().lower()
        duplicate = db.session.scalar(
            select(User.id).where(
                func.lower(User.username) == username,
                User.id != user.id,
            )
        )
        if duplicate is not None:
            abort(409, description="That username is already in use.")
        user.username = username
    if "bio" in data:
        user.bio = data["bio"]
    if "website" in data:
        user.website = data["website"]
    if "social_links" in data:
        user.social_links = data["social_links"]

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="The profile conflicts with an existing account.")
    return json_response({**user_summary(user), **_public_profile(user)})


@users_api.delete("/me")
@authenticated
def delete_my_account(user: User):
    data = load_json(PasswordConfirmationSchema())
    if not user.check_password(data["current_password"]):
        abort(400, description="The current password is incorrect.")

    user.is_active = False
    user.deleted_at = utcnow()
    user.auth_token_version += 1
    user.username = f"deleted_{user.id.hex[:20]}"
    user.email = f"deleted+{user.id.hex}@invalid.local"
    user.bio = None
    user.website = None
    user.social_links = {}
    user.set_password(secrets.token_urlsafe(48))
    db.session.commit()
    return "", 204


@users_api.get("/<username>")
def get_public_profile(username: str):
    user = db.session.scalar(
        select(User).where(
            func.lower(User.username) == username.lower(),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    if user is None:
        abort(404, description="The requested profile was not found.")
    return json_response(_public_profile(user))
