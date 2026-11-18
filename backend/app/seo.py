"""Public search-engine discovery documents."""

from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement, tostring

from flask import Blueprint, current_app, make_response
from sqlalchemy import select

from backend.app.core.extensions import db
from backend.app.models.enums import PostStatus
from backend.app.models.post import Post
from backend.app.models.user import User

seo = Blueprint("seo", __name__)
_SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"


@seo.get("/sitemap.xml")
def sitemap():
    base_url = current_app.config["FRONTEND_BASE_URL"].rstrip("/")
    root = Element("urlset", xmlns=_SITEMAP_NAMESPACE)
    posts = db.session.scalars(
        select(Post)
        .join(Post.author)
        .where(
            Post.status == PostStatus.PUBLISHED,
            Post.published_at.is_not(None),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .order_by(Post.published_at.desc(), Post.id)
    )
    for post in posts:
        entry = SubElement(root, "url")
        SubElement(entry, "loc").text = f"{base_url}/posts/{post.slug}"
        SubElement(entry, "lastmod").text = post.updated_at.date().isoformat()

    response = make_response(
        tostring(root, encoding="utf-8", xml_declaration=True),
        200,
    )
    response.mimetype = "application/xml"
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@seo.get("/robots.txt")
def robots():
    base_url = current_app.config["FRONTEND_BASE_URL"].rstrip("/")
    response = make_response(
        "\n".join(
            (
                "User-agent: *",
                "Disallow: /api/v1/admin",
                "Disallow: /api/v1/users/me",
                f"Sitemap: {base_url}/sitemap.xml",
                "",
            )
        ),
        200,
    )
    response.mimetype = "text/plain"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response
