"""Email notification helpers."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from .config import get_settings
from .models import WatchRule

logger = logging.getLogger("pickleball_scraper")


def send_email_alert(*, watch: WatchRule, subject: str, body: str) -> bool:
    """Send an alert email for a watch rule."""
    settings = get_settings()
    if not settings.smtp_enabled:
        return False
    if not settings.smtp_host:
        logger.warning("SMTP host not configured; skipping email send")
        return False
    if not watch.contact:
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_address
    msg["To"] = watch.contact
    msg.set_content(body)

    try:
        if settings.smtp_use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.starttls(context=context)
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
        logger.info("Sent alert email to %s", watch.contact)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send alert email: %s", exc, exc_info=True)
        return False
