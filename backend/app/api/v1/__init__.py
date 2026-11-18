"""Version 1 REST API blueprint and route registration."""

from flask import Blueprint

from backend.app.api.v1.admin import admin_api, reports_api
from backend.app.api.v1.auth import auth_api
from backend.app.api.v1.comments import comments_api
from backend.app.api.v1.posts import posts_api
from backend.app.api.v1.social import social_api
from backend.app.api.v1.taxonomy import taxonomy_api
from backend.app.api.v1.uploads import uploads_api
from backend.app.api.v1.users import users_api

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")
api_v1.register_blueprint(auth_api, url_prefix="/auth")
api_v1.register_blueprint(posts_api, url_prefix="/posts")
api_v1.register_blueprint(comments_api)
api_v1.register_blueprint(taxonomy_api)
api_v1.register_blueprint(social_api)
api_v1.register_blueprint(users_api, url_prefix="/users")
api_v1.register_blueprint(uploads_api)
api_v1.register_blueprint(admin_api, url_prefix="/admin")
api_v1.register_blueprint(reports_api, url_prefix="/reports")
