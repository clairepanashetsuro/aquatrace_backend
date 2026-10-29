import smtplib
import ssl
from email.message import EmailMessage

from core.config import settings


class EmailDeliveryError(Exception):
    pass


def send_password_reset_otp(to_email: str, otp: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_email:
        raise EmailDeliveryError("Email delivery is not configured")

    if bool(settings.smtp_username) != bool(settings.smtp_password):
        raise EmailDeliveryError("SMTP credentials are incomplete")

    message = EmailMessage()
    message["Subject"] = "AquaTrace Password Reset Code"
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message.set_content(
        f"""Your AquaTrace password reset code is: {otp}

This code expires in 10 minutes.

If you did not request a password reset, you can ignore this email.

Do not share this code with anyone."""
    )

    try:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=10,
        ) as server:
            if settings.smtp_use_tls:
                server.starttls(context=ssl.create_default_context())

            if settings.smtp_username and settings.smtp_password:
                server.login(
                    settings.smtp_username,
                    settings.smtp_password,
                )

            server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailDeliveryError("Unable to deliver password reset email") from exc
