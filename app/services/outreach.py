"""Notify the platform owner when a kitchen joins the waitlist."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User

logger = get_logger("aahaar.outreach")


def _waitlist_body(user: User) -> str:
    phone = user.phone or "not provided"
    return (
        f"{user.full_name} joined the Aahaar waitlist.\n"
        f"Email: {user.email}\n"
        f"Phone: {phone}\n"
        f"Approve them from the Super Admin panel."
    )


def _send_email_sync(user: User) -> None:
    to_addr = settings.admin_notify_email.strip()
    user_name = settings.smtp_user.strip()
    password = settings.smtp_password.strip()
    if not to_addr or not user_name or not password:
        logger.info("Waitlist email skipped (SMTP not configured) for %s", user.email)
        return

    from_addr = settings.smtp_from_email.strip() or user_name
    message = EmailMessage()
    message["Subject"] = f"Aahaar waitlist: {user.full_name}"
    message["From"] = from_addr
    message["To"] = to_addr
    message.set_content(_waitlist_body(user))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(user_name, password)
        smtp.send_message(message)
    logger.info("Waitlist email sent for %s", user.email)


async def _send_whatsapp(user: User) -> None:
    sid = settings.twilio_account_sid.strip()
    token = settings.twilio_auth_token.strip()
    from_number = settings.twilio_whatsapp_from.strip()
    to_number = settings.admin_whatsapp_to.strip()
    if not sid or not token or not from_number or not to_number:
        logger.info("Waitlist WhatsApp skipped (Twilio not configured) for %s", user.email)
        return

    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    payload = urlencode({"From": from_number, "To": to_number, "Body": _waitlist_body(user)})
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            url,
            content=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(sid, token),
        )
    if response.status_code >= 400:
        logger.warning("Waitlist WhatsApp failed (%s): %s", response.status_code, response.text)
        return
    logger.info("Waitlist WhatsApp sent for %s", user.email)


async def notify_waitlist_join(user: User) -> None:
    logger.info("Waitlist join: %s <%s> phone=%s", user.full_name, user.email, user.phone)
    try:
        await asyncio.to_thread(_send_email_sync, user)
    except Exception:
        logger.exception("Waitlist email failed for %s", user.email)
    try:
        await _send_whatsapp(user)
    except Exception:
        logger.exception("Waitlist WhatsApp failed for %s", user.email)
