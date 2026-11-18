from __future__ import annotations

from io import BytesIO
from uuid import UUID, uuid4

import pytest
from flask_jwt_extended import create_access_token
from PIL import Image

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
            "RATELIMIT_ENABLED": False,
            "SECRET_KEY": "test-secret-key-longer-than-thirty-two-bytes",
            "JWT_SECRET_KEY": "different-test-secret-longer-than-thirty-two-bytes",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        }
    )
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def _create_user(app, username: str, role: UserRole = UserRole.USER) -> tuple[UUID, str]:
    with app.app_context():
        user = User(username=username, email=f"{username}@example.com", role=role)
        user.set_password("a-long-test-password")
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        token = create_access_token(
            identity=str(user_id),
            additional_claims={"role": user.role.value, "auth_version": user.auth_token_version},
        )
        return user_id, token


def _png_bytes() -> bytes:
    image = Image.new("RGB", (20, 10), color="blue")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_avatar_upload_is_normalized_and_served_safely(app):
    user_id, token = _create_user(app, "writer")
    client = app.test_client()

    response = client.post(
        "/api/v1/users/me/avatar",
        headers={"Authorization": f"Bearer {token}"},
        data={"image": (BytesIO(_png_bytes()), "avatar.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    avatar_url = response.json["data"]["avatar_url"]
    image_response = client.get(avatar_url)
    assert image_response.status_code == 200
    assert image_response.mimetype == "image/png"
    assert image_response.headers["X-Content-Type-Options"] == "nosniff"
    with Image.open(BytesIO(image_response.data)) as stored_image:
        assert stored_image.size == (20, 10)

    with app.app_context():
        assert db.session.get(User, user_id).avatar_url == avatar_url


def test_avatar_upload_rejects_mismatched_and_oversized_files(app):
    _, token = _create_user(app, "writer")
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}

    mismatch = client.post(
        "/api/v1/users/me/avatar",
        headers=headers,
        data={"image": (BytesIO(_png_bytes()), "avatar.jpg")},
        content_type="multipart/form-data",
    )
    assert mismatch.status_code == 400

    app.config["MAX_IMAGE_UPLOAD_BYTES"] = 32
    oversized = client.post(
        "/api/v1/users/me/avatar",
        headers=headers,
        data={"image": (BytesIO(b"x" * 33), "avatar.png")},
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 413


def test_cover_upload_requires_post_ownership(app):
    owner_id, _ = _create_user(app, "owner", UserRole.AUTHOR)
    _, other_token = _create_user(app, "other")
    post_id = uuid4()
    with app.app_context():
        db.session.add(
            Post(
                id=post_id,
                author_id=owner_id,
                title="A post",
                slug="a-post",
                content_html="Post body",
                status=PostStatus.DRAFT,
            )
        )
        db.session.commit()

    response = app.test_client().post(
        f"/api/v1/posts/{post_id}/cover",
        headers={"Authorization": f"Bearer {other_token}"},
        data={"image": (BytesIO(_png_bytes()), "cover.png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 403
