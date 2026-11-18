"""Version 1 REST API blueprint and route registration."""

from flask import Blueprint

from backend.app.api.v1.auth import auth_api
from backend.app.api.v1.users import users_api

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
api_v1.register_blueprint(auth_api, url_prefix="/auth")
api_v1.register_blueprint(users_api, url_prefix="/users")
