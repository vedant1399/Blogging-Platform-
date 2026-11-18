"""Environment-backed Flask configuration."""

import os
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def _environment_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _allowed_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]


def _database_uri() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return f"sqlite:///{(PROJECT_ROOT / 'instance' / 'blogging-platform.db').as_posix()}"
    if database_url.startswith(("postgres://", "postgresql://")):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1).replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    return database_url


class BaseConfig:
    """Settings shared by all runtime environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "local-development-secret-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "local-development-jwt-secret-change-me")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS: dict[str, Any] = {"pool_pre_ping": True}

    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_COOKIE_SECURE = _environment_bool("JWT_COOKIE_SECURE", False)
    JWT_COOKIE_SAMESITE = os.getenv("JWT_COOKIE_SAMESITE", "Lax")
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_COOKIE_HTTPONLY = True
    JWT_REFRESH_COOKIE_NAME = "refresh_token"
    JWT_REFRESH_COOKIE_PATH = "/api/v1/auth"
    JWT_REFRESH_COOKIE_HTTPONLY = True

    WTF_CSRF_ENABLED = True
    WTF_CSRF_CHECK_DEFAULT = False

    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(5 * 1024 * 1024)))
    MAX_IMAGE_UPLOAD_BYTES = int(os.getenv("MAX_IMAGE_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(PROJECT_ROOT / "instance" / "uploads"))
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

    CORS_ORIGINS = _allowed_origins()
    CORS_SUPPORTS_CREDENTIALS = True
    CACHE_TYPE = "RedisCache" if os.getenv("REDIS_URL") else "SimpleCache"
    CACHE_REDIS_URL = os.getenv("REDIS_URL")
    CACHE_DEFAULT_TIMEOUT = int(os.getenv("CACHE_DEFAULT_TIMEOUT", "300"))
    RATELIMIT_STORAGE_URI = os.getenv("REDIS_URL", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = _environment_bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _environment_bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")
    FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _environment_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    PREFERRED_URL_SCHEME = "http"


class DevelopmentConfig(BaseConfig):
    """Local development settings."""

    DEBUG = True


class TestingConfig(BaseConfig):
    """Isolated settings for automated tests."""

    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    CACHE_TYPE = "SimpleCache"
    RATELIMIT_ENABLED = False
    CORS_ORIGINS = ["http://localhost:5173"]


class ProductionConfig(BaseConfig):
    """Hardened settings for production deployments."""

    DEBUG = False
    PREFERRED_URL_SCHEME = "https"
    SESSION_COOKIE_SECURE = True
    JWT_COOKIE_SECURE = True
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    @classmethod
    def validate(cls) -> None:
        """Fail startup when required production settings are missing or unsafe."""
        secret_key = os.getenv("SECRET_KEY", "")
        jwt_secret_key = os.getenv("JWT_SECRET_KEY", "")
        database_url = os.getenv("DATABASE_URL", "")
        redis_url = os.getenv("REDIS_URL", "")
        frontend_base_url = os.getenv("FRONTEND_BASE_URL", "")
        origins = _allowed_origins()

        missing = [
            name
            for name, value in (
                ("SECRET_KEY", secret_key),
                ("JWT_SECRET_KEY", jwt_secret_key),
                ("DATABASE_URL", database_url),
                ("REDIS_URL", redis_url),
                ("MAIL_SERVER", os.getenv("MAIL_SERVER", "")),
                ("MAIL_DEFAULT_SENDER", os.getenv("MAIL_DEFAULT_SENDER", "")),
                ("FRONTEND_BASE_URL", frontend_base_url),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing required production environment variables: "
                + ", ".join(missing)
            )
        if secret_key == jwt_secret_key:
            raise RuntimeError("SECRET_KEY and JWT_SECRET_KEY must be different values.")
        if len(secret_key.encode("utf-8")) < 32 or len(jwt_secret_key.encode("utf-8")) < 32:
            raise RuntimeError("Production signing keys must each be at least 32 bytes.")
        if not _database_uri().startswith("postgresql+psycopg://"):
            raise RuntimeError(
                "Production DATABASE_URL must use PostgreSQL with the psycopg driver."
            )
        if any(origin == "*" for origin in origins):
            raise RuntimeError("CORS_ORIGINS must not contain a wildcard in production.")
        if not origins:
            raise RuntimeError("CORS_ORIGINS must contain at least one trusted origin.")
        if any(urlparse(origin).scheme != "https" for origin in origins):
            raise RuntimeError("Every production CORS_ORIGINS entry must use HTTPS.")
        if urlparse(frontend_base_url).scheme != "https":
            raise RuntimeError("FRONTEND_BASE_URL must use HTTPS in production.")


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config() -> type[BaseConfig]:
    """Resolve the requested config using APP_ENV."""
    environment = os.getenv("APP_ENV", "development").strip().lower()
    try:
        return CONFIG_BY_NAME[environment]
    except KeyError as error:
        valid_environments = ", ".join(sorted(CONFIG_BY_NAME))
        raise RuntimeError(
            f"Unsupported APP_ENV {environment!r}; expected one of: {valid_environments}."
        ) from error
