"""Transactional mail delivery for account security workflows."""

from smtplib import SMTPException
from urllib.parse import quote

from flask import current_app
from flask_mail import Message

from backend.app.core.extensions import mail
from backend.app.models.user import User


class EmailDeliveryError(RuntimeError):
    """Raised when account security mail cannot be delivered."""


def send_account_action_email(user: User, purpose: str, token: str) -> None:
    if not current_app.config.get("MAIL_SERVER") or not current_app.config.get(
        "MAIL_DEFAULT_SENDER"
    ):
        raise EmailDeliveryError("Email delivery is not configured.")

    base_url = current_app.config["FRONTEND_BASE_URL"].rstrip("/")
    if purpose == "verify-email":
        action_url = f"{base_url}/verify-email?token={quote(token)}"
        subject = "Verify your Ink & Insight email"
        action = "verify your email address"
    elif purpose == "reset-password":
        action_url = f"{base_url}/reset-password?token={quote(token)}"
        subject = "Reset your Ink & Insight password"
        action = "reset your password"
    else:
        raise ValueError(f"Unsupported account email purpose: {purpose}")

    message = Message(
        subject=subject,
        recipients=[user.email],
        body=(
            f"Hello {user.username},\n\n"
            f"Use the following link to {action}:\n{action_url}\n\n"
            "If you did not request this, you can ignore this message."
        ),
    )
    try:
        mail.send(message)
    except (SMTPException, OSError) as error:
        raise EmailDeliveryError("The account email could not be delivered.") from error
