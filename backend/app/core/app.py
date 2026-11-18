"""Flask application factory and common HTTP handlers."""

import logging
import os
from typing import Any

from flask import Flask, jsonify, request
from marshmallow import ValidationError
from sqlalchemy import select
from werkzeug.exceptions import HTTPException
from flask_wtf.csrf import generate_csrf

from backend.app.core.config import ProductionConfig, get_config
from backend.app.core.extensions import (
    cache,
    cors,
    csrf,
    db,
    jwt,
    limiter,
    login_manager,
    mail,
    migrate,
    talisman,
)
from backend.app.models.security import TokenRevocation


def create_app(config_object: type | dict[str, Any] | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    if isinstance(config_object, dict):
        selected_config = get_config()
        app.config.from_object(selected_config)
        app.config.update(config_object)
    else:
        selected_config = config_object or get_config()
        app.config.from_object(selected_config)

    if selected_config is ProductionConfig:
        ProductionConfig.validate()
    elif (
        app.config.get("DEBUG")
        and app.config["SECRET_KEY"] == get_config().SECRET_KEY
    ):
        app.logger.warning(
            "Using the local development SECRET_KEY. Set SECRET_KEY outside development."
        )

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    _configure_logging(app)
    _initialize_extensions(app)
    _register_csrf_protection(app)
    _register_error_handlers(app)
    _register_api_routes(app)
    _register_health_endpoint(app)
    return app


def _configure_logging(app: Flask) -> None:
    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO)


def _initialize_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    cache.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=app.config["CORS_SUPPORTS_CREDENTIALS"],
    )
    talisman.init_app(
        app,
        force_https=not app.debug and not app.testing,
        content_security_policy={
            "default-src": "'none'",
            "frame-ancestors": "'none'",
            "base-uri": "'none'",
        },
        strict_transport_security=not app.debug and not app.testing,
        session_cookie_secure=app.config["SESSION_COOKIE_SECURE"],
    )

    @jwt.token_in_blocklist_loader
    def is_token_revoked(_jwt_header: dict, jwt_payload: dict) -> bool:
        return (
            db.session.scalar(
                select(TokenRevocation.id).where(
                    TokenRevocation.jti == jwt_payload["jti"]
                )
            )
            is not None
        )


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError):
        return (
            jsonify(
                {
                    "error": {
                        "code": "validation_error",
                        "message": "The request data is invalid.",
                        "details": error.messages,
                    }
                }
            ),
            400,
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        response = jsonify(
            {
                "error": {
                    "code": error.name.lower().replace(" ", "_"),
                    "message": error.description,
                }
            }
        )
        response.status_code = error.code or 500
        return response

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled application error")
        return (
            jsonify(
                {
                    "error": {
                        "code": "internal_server_error",
                        "message": "An unexpected error occurred.",
                    }
                }
            ),
            500,
        )

    @app.errorhandler(429)
    def handle_rate_limit_error(error: HTTPException):
        response = jsonify(
            {
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests. Please try again later.",
                }
            }
        )
        response.status_code = error.code or 429
        return response


def _register_health_endpoint(app: Flask) -> None:
    @app.get("/api/v1/csrf")
    def csrf_token():
        return jsonify({"csrf_token": generate_csrf()}), 200

    @app.get("/api/v1/health")
    def health_check():
        return jsonify({"status": "ok"}), 200


def _register_api_routes(app: Flask) -> None:
    from backend.app.api.v1 import api_v1

    app.register_blueprint(api_v1)


def _register_csrf_protection(app: Flask) -> None:
    @app.before_request
    def protect_cookie_authenticated_requests():
        if (
            request.path.startswith("/api/")
            and request.method in app.config["WTF_CSRF_METHODS"]
            and not request.headers.get("Authorization", "").startswith("Bearer ")
        ):
            csrf.protect()
