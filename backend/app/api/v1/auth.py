"""Account registration, authentication, token, and recovery endpoints."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from flask import Blueprint, abort, current_app, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_refresh_cookies,
    unset_refresh_cookies,
)
from flask_jwt_extended.exceptions import JWTExtendedException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from backend.app.api.v1.common import (
    current_user,
    json_response,
    load_json,
    revoke_token,
    token_response,
    user_summary,
)
from backend.app.api.v1.schemas import (
    ChangePasswordSchema,
    LoginSchema,
    PasswordResetRequestSchema,
    PasswordResetSchema,
    RegistrationSchema,
    VerifyEmailSchema,
)
from backend.app.core.extensions import db, limiter
from backend.app.models.enums import UserRole
from backend.app.models.mixins import utcnow
from backend.app.models.security import TokenRevocation
from backend.app.models.user import User
from backend.app.services.email import EmailDeliveryError, send_account_action_email

auth_api = Blueprint("auth", __name__)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= utcnow()


@auth_api.post("/register")
@limiter.limit("3 per hour")
def register():
    data = load_json(RegistrationSchema())
    email = data["email"].strip().lower()
    username = data["username"].strip().lower()
    exists = db.session.scalar(
        select(User.id).where(
            (func.lower(User.email) == email) | (func.lower(User.username) == username)
        )
    )
    if exists is not None:
        abort(409, description="That email address or username is already registered.")

    verification_token = secrets.token_urlsafe(32)
    user = User(username=username, email=email, role=UserRole.USER)
    user.set_password(data["password"])
    user.email_verification_token_hash = _token_hash(verification_token)
    user.email_verification_expires_at = utcnow() + timedelta(hours=24)
    db.session.add(user)
    try:
        db.session.flush()
        send_account_action_email(user, "verify-email", verification_token)
        db.session.commit()
    except EmailDeliveryError as error:
        db.session.rollback()
        abort(503, description=str(error))
    except IntegrityError:
        db.session.rollback()
        abort(409, description="That email address or username is already registered.")

    return json_response(
        {"message": "Check your email to verify your account."},
        201,
    )


@auth_api.post("/verify-email")
@limiter.limit("10 per hour")
def verify_email():
    data = load_json(VerifyEmailSchema())
    token_hash = _token_hash(data["token"])
    user = db.session.scalar(
        select(User).where(User.email_verification_token_hash == token_hash)
    )
    if (
        user is None
        or user.email_verification_expires_at is None
        or _is_expired(user.email_verification_expires_at)
    ):
        abort(400, description="The verification token is invalid or expired.")

    user.is_email_verified = True
    user.email_verified_at = utcnow()
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    db.session.commit()
    return json_response({"message": "Email address verified."})


@auth_api.post("/login")
@limiter.limit("10 per minute")
def login():
    data = load_json(LoginSchema())
    user = db.session.scalar(
        select(User).where(func.lower(User.email) == data["email"].strip().lower())
    )
    if user is None or not user.check_password(data["password"]):
        abort(401, description="Invalid email address or password.")
    if not user.is_active or user.deleted_at is not None:
        abort(401, description="This account is unavailable.")
    if not user.is_email_verified:
        abort(403, description="Verify your email address before signing in.")

    user.last_login_at = utcnow()
    db.session.commit()
    return token_response(user)


@auth_api.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    claims = get_jwt()
    try:
        user_id = UUID(get_jwt_identity())
    except (TypeError, ValueError):
        abort(401, description="Authentication is required.")
    user = db.session.get(User, user_id)
    if (
        user is None
        or not user.is_active
        or user.deleted_at is not None
        or claims.get("auth_version") != user.auth_token_version
    ):
        abort(401, description="Authentication is required.")

    revoke_token(claims, user.id)
    token_claims = {
        "role": user.role.value,
        "auth_version": user.auth_token_version,
    }
    access_token = create_access_token(
        identity=str(user.id),
        additional_claims=token_claims,
    )
    refresh_token = create_refresh_token(
        identity=str(user.id),
        additional_claims=token_claims,
    )
    db.session.commit()
    response, status = json_response(
        {"access_token": access_token, "token_type": "Bearer"}
    )
    set_refresh_cookies(response, refresh_token)
    return response, status


@auth_api.post("/logout")
@jwt_required()
def logout():
    user = current_user()
    access_claims = get_jwt()
    refresh_cookie = request.cookies.get(
        current_app.config["JWT_REFRESH_COOKIE_NAME"]
    )
    refresh_claims = None
    if refresh_cookie:
        try:
            refresh_claims = decode_token(refresh_cookie)
        except JWTExtendedException as error:
            abort(400, description="The refresh token cookie is invalid.")

    revoke_token(access_claims, user.id)
    if refresh_claims and refresh_claims.get("sub") == str(user.id):
        revoke_token(refresh_claims, user.id)
    db.session.commit()
    response, status = json_response({"message": "Signed out."})
    unset_refresh_cookies(response)
    return response, status


@auth_api.post("/password-reset/request")
@limiter.limit("5 per hour")
def request_password_reset():
    data = load_json(PasswordResetRequestSchema())
    email = data["email"].strip().lower()
    user = db.session.scalar(
        select(User).where(func.lower(User.email) == email, User.is_active.is_(True))
    )
    if user is None or user.deleted_at is not None:
        return json_response(
            {"message": "If the account exists, password reset instructions will be sent."},
            202,
        )

    reset_token = secrets.token_urlsafe(32)
    user.password_reset_token_hash = _token_hash(reset_token)
    user.password_reset_expires_at = utcnow() + timedelta(minutes=30)
    db.session.commit()
    try:
        send_account_action_email(user, "reset-password", reset_token)
    except EmailDeliveryError as error:
        current_app.logger.error("Password-reset email delivery failed: %s", error)
        abort(503, description="Password-reset email delivery is unavailable.")
    return json_response(
        {"message": "If the account exists, password reset instructions will be sent."},
        202,
    )


@auth_api.post("/password-reset/confirm")
@limiter.limit("10 per hour")
def confirm_password_reset():
    data = load_json(PasswordResetSchema())
    token_hash = _token_hash(data["token"])
    user = db.session.scalar(
        select(User).where(User.password_reset_token_hash == token_hash)
    )
    if (
        user is None
        or user.password_reset_expires_at is None
        or _is_expired(user.password_reset_expires_at)
        or not user.is_active
    ):
        abort(400, description="The password-reset token is invalid or expired.")

    user.set_password(data["password"])
    user.auth_token_version += 1
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    db.session.commit()
    return json_response({"message": "Password reset successfully."})


@auth_api.post("/password")
@jwt_required()
@limiter.limit("5 per minute")
def change_password():
    user = current_user()
    data = load_json(ChangePasswordSchema())
    if not user.check_password(data["current_password"]):
        abort(400, description="The current password is incorrect.")
    if check_password_hash(user.password_hash, data["new_password"]):
        abort(400, description="Choose a password different from the current password.")

    user.set_password(data["new_password"])
    user.auth_token_version += 1
    db.session.commit()
    return token_response(user)
