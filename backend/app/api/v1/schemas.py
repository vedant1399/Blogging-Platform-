"""Input schemas for authentication and profile endpoints."""

from marshmallow import RAISE, Schema, fields, validate


class StrictSchema(Schema):
    class Meta:
        unknown = RAISE


class RegistrationSchema(StrictSchema):
    username = fields.Str(
        required=True,
        validate=validate.Regexp(r"^[A-Za-z0-9_]{3,30}$"),
    )
    email = fields.Email(required=True, validate=validate.Length(max=254))
    password = fields.Str(required=True, validate=validate.Length(min=12, max=128))


class LoginSchema(StrictSchema):
    email = fields.Email(required=True, validate=validate.Length(max=254))
    password = fields.Str(required=True, validate=validate.Length(min=1, max=128))


class VerifyEmailSchema(StrictSchema):
    token = fields.Str(required=True, validate=validate.Length(min=32, max=256))


class PasswordResetRequestSchema(StrictSchema):
    email = fields.Email(required=True, validate=validate.Length(max=254))


class PasswordResetSchema(StrictSchema):
    token = fields.Str(required=True, validate=validate.Length(min=32, max=256))
    password = fields.Str(required=True, validate=validate.Length(min=12, max=128))


class ChangePasswordSchema(StrictSchema):
    current_password = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    new_password = fields.Str(required=True, validate=validate.Length(min=12, max=128))


class PasswordConfirmationSchema(StrictSchema):
    current_password = fields.Str(required=True, validate=validate.Length(min=1, max=128))


class ProfileUpdateSchema(StrictSchema):
    username = fields.Str(validate=validate.Regexp(r"^[A-Za-z0-9_]{3,30}$"))
    bio = fields.Str(allow_none=True, validate=validate.Length(max=500))
    website = fields.Url(allow_none=True, schemes={"http", "https"})
    social_links = fields.Dict(
        keys=fields.Str(validate=validate.Length(max=40)),
        values=fields.Url(schemes={"http", "https"}),
    )


class PostWriteSchema(StrictSchema):
    title = fields.Str(validate=validate.Length(min=1, max=240))
    slug = fields.Str(validate=validate.Regexp(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"))
    excerpt = fields.Str(allow_none=True, validate=validate.Length(max=500))
    content_html = fields.Str()
    content_json = fields.Dict(allow_none=True)
    cover_image_url = fields.Url(allow_none=True, schemes={"http", "https"})
    meta_description = fields.Str(allow_none=True, validate=validate.Length(max=320))
    seo_keywords = fields.List(
        fields.Str(validate=validate.Length(max=50)),
        validate=validate.Length(max=20),
    )
    canonical_url = fields.Url(allow_none=True, schemes={"http", "https"})
    status = fields.Str(
        validate=validate.OneOf(["draft", "scheduled", "published", "archived"])
    )
    scheduled_at = fields.DateTime(allow_none=True)
    allow_comments = fields.Bool()
    category_ids = fields.List(
        fields.UUID(),
        validate=validate.Length(max=20),
    )
    tag_ids = fields.List(
        fields.UUID(),
        validate=validate.Length(max=100),
    )


class CommentWriteSchema(StrictSchema):
    body = fields.Str(required=True, validate=validate.Length(min=1, max=5000))
    parent_id = fields.UUID(allow_none=True)


class CategoryWriteSchema(StrictSchema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    slug = fields.Str(validate=validate.Regexp(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"))
    description = fields.Str(allow_none=True, validate=validate.Length(max=2000))


class TagWriteSchema(StrictSchema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=60))
    slug = fields.Str(validate=validate.Regexp(r"^[a-z0-9]+(?:-[a-z0-9]+)*$"))


class ReportWriteSchema(StrictSchema):
    target_type = fields.Str(
        required=True,
        validate=validate.OneOf(["user", "post", "comment"]),
    )
    target_id = fields.UUID(required=True)
    reason = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    details = fields.Str(allow_none=True, validate=validate.Length(max=5000))


class ReportReviewSchema(StrictSchema):
    status = fields.Str(
        required=True,
        validate=validate.OneOf(["reviewed", "dismissed"]),
    )
    resolution = fields.Str(allow_none=True, validate=validate.Length(max=5000))


class UserRoleUpdateSchema(StrictSchema):
    role = fields.Str(
        required=True,
        validate=validate.OneOf(["user", "author", "admin"]),
    )
