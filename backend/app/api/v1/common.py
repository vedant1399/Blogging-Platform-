"""Shared request validation, authentication, and response helpers."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable
from uuid import UUID

from flask import abort, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_refresh_cookies,
)
from marshmallow import Schema, ValidationError
from sqlalchemy import select

from backend.app.core.extensions import db
from backend.app.models.enums import UserRole
from backend.app.models.user import User


def load_json(schema: Schema) -> dict[str, Any]:
    if not request.is_json:
        abort(415, description="Content-Type must be application/json.")
    payload = request.get_json()
    if not isinstance(payload, dict):
        raise ValidationError({"_schema": ["Expected a JSON object."]})
    return schema.load(payload)


def json_response(data: Any, status: int = 200):
    return jsonify({"data": data}), status


def user_summary(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "is_email_verified": user.is_email_verified,
        "avatar_url": user.avatar_url,
    }


def token_response(user: User, status: int = 200):
    additional_claims = {
        "role": user.role.value,
        "auth_version": user.auth_token_version,
    }
    access_token = create_access_token(
        identity=str(user.id),
        fresh=True,
        additional_claims=additional_claims,
    )
    refresh_token = create_refresh_token(
        identity=str(user.id),
        additional_claims=additional_claims,
    )
    response, response_status = json_response(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "user": user_summary(user),
        },
        status,
    )
    set_refresh_cookies(response, refresh_token)
    return response, response_status


def current_user() -> User:
    identity = get_jwt_identity()
    try:
        user_id = UUID(identity)
    except (TypeError, ValueError):
        abort(401, description="Authentication is required.")

    user = db.session.get(User, user_id)
    if (
        user is None
        or not user.is_active
        or user.deleted_at is not None
        or get_jwt().get("auth_version") != user.auth_token_version
    ):
        abort(401, description="Authentication is required.")
    return user


def authenticated(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    @jwt_required()
    def wrapped(*args: Any, **kwargs: Any):
        return view(current_user(), *args, **kwargs)

    return wrapped


def roles_required(*roles: UserRole):
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def check_role(user: User, *args: Any, **kwargs: Any):
            if user.role not in roles:
                abort(403, description="You do not have permission to perform this action.")
            return view(user, *args, **kwargs)

        return authenticated(check_role)

    return decorator


def revoke_token(token_claims: dict[str, Any], user_id: UUID) -> None:
    from backend.app.models.security import TokenRevocation

    jti = token_claims["jti"]
    existing = db.session.scalar(
        select(TokenRevocation.id).where(TokenRevocation.jti == jti)
    )
    if existing is None:
        from datetime import UTC, datetime

        db.session.add(
            TokenRevocation(
                jti=jti,
                token_type=token_claims["type"],
                user_id=user_id,
                expires_at=datetime.fromtimestamp(token_claims["exp"], UTC),
            )
        )
