from __future__ import annotations

from datetime import UTC, datetime
from xml.etree import ElementTree

import pytest

from backend.app import create_app
from backend.app.core.extensions import db
from backend.app.models.enums import PostStatus, UserRole
from backend.app.models.post import Post
from backend.app.models.user import User


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-longer-than-thirty-two-bytes",
            "JWT_SECRET_KEY": "different-test-secret-longer-than-thirty-two-bytes",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "FRONTEND_BASE_URL": "https://blog.example",
        }
    )
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def test_sitemap_includes_only_published_posts_by_active_authors(app):
    with app.app_context():
        author = User(username="author", email="author@example.com", role=UserRole.AUTHOR)
        author.set_password("a-long-test-password")
        disabled = User(
            username="disabled",
            email="disabled@example.com",
            role=UserRole.AUTHOR,
            is_active=False,
        )
        disabled.set_password("a-long-test-password")
        db.session.add_all([author, disabled])
        db.session.flush()
        db.session.add_all(
            [
                Post(
                    author=author,
                    title="Public",
                    slug="public-post",
                    content_html="Published content",
                    status=PostStatus.PUBLISHED,
                    published_at=datetime.now(UTC),
                ),
                Post(
                    author=author,
                    title="Draft",
                    slug="draft-post",
                    content_html="Draft content",
                    status=PostStatus.DRAFT,
                ),
                Post(
                    author=disabled,
                    title="Inactive",
                    slug="inactive-post",
                    content_html="Unavailable content",
                    status=PostStatus.PUBLISHED,
                    published_at=datetime.now(UTC),
                ),
            ]
        )
        db.session.commit()

    response = app.test_client().get("/sitemap.xml")

    assert response.status_code == 200
    assert response.mimetype == "application/xml"
    root = ElementTree.fromstring(response.data)
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locations = [node.text for node in root.findall("s:url/s:loc", namespace)]
    assert locations == ["https://blog.example/posts/public-post"]


def test_robots_points_to_public_sitemap_and_excludes_private_routes(app):
    response = app.test_client().get("/robots.txt")

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert "Disallow: /api/v1/admin" in response.text
    assert "Disallow: /api/v1/users/me" in response.text
    assert "Sitemap: https://blog.example/sitemap.xml" in response.text
