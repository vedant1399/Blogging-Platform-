"""Operational Flask CLI commands."""

import click
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.app.core.extensions import db
from backend.app.models.enums import UserRole
from backend.app.models.mixins import utcnow
from backend.app.models.user import User
from backend.app.services.publishing import publish_due_posts


def register_cli_commands(app) -> None:
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--username", prompt=True)
    def create_admin(email: str, username: str) -> None:
        """Create the initial administrator account from a trusted shell."""
        normalized_email = email.strip().lower()
        normalized_username = username.strip().lower()
        existing = db.session.scalar(
            select(User.id).where(
                (func.lower(User.email) == normalized_email)
                | (func.lower(User.username) == normalized_username)
            )
        )
        if existing is not None:
            raise click.ClickException("That email address or username is already in use.")

        password = click.prompt(
            "Administrator password",
            hide_input=True,
            confirmation_prompt=True,
        )
        if len(password) < 12:
            raise click.ClickException("The password must contain at least 12 characters.")

        admin = User(
            username=normalized_username,
            email=normalized_email,
            role=UserRole.ADMIN,
            is_active=True,
            is_email_verified=True,
            email_verified_at=utcnow(),
        )
        admin.set_password(password)
        db.session.add(admin)
        try:
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            raise click.ClickException(
                "The account conflicts with an existing user."
            ) from error
        click.echo(f"Administrator account created for {normalized_email}.")

    @app.cli.command("publish-scheduled")
    def publish_scheduled() -> None:
        """Publish posts whose scheduled time has arrived."""
        count = publish_due_posts()
        click.echo(f"Published {count} scheduled post(s).")
