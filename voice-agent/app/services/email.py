"""Async email notification service.

Provides three public functions for sending appointment-related emails.
All functions are fire-and-forget safe: exceptions are caught and logged,
never raised. The webhook response is never blocked by email failures.
"""
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import aiosmtplib

from app.config import get_settings

__all__ = ["send_caller_confirmation", "send_owner_alert", "send_callback_request"]

logger = logging.getLogger(__name__)

_REASON_LABELS: dict[str, str] = {
    "no_slot_found": "No available appointment slots could be found",
    "cannot_understand": "Agent was unable to understand the caller after multiple attempts",
    "caller_requested": "Caller explicitly requested to speak with someone",
}


async def _send(to_address: str, subject: str, body: str) -> None:
    """Internal helper: compose and send a plain-text email via SMTP."""
    settings = get_settings()
    if not settings.smtp_host:
        logger.debug("SMTP not configured; skipping email to %s", to_address)
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from_address
        msg["To"] = to_address
        msg.attach(MIMEText(body, "plain"))
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("Email sent to %s: %s", to_address, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_address, exc)


def _format_dt(appointment_dt: datetime, business_timezone: str) -> str:
    """Format a datetime in the given timezone as a human-readable string."""
    tz = ZoneInfo(business_timezone)
    return appointment_dt.astimezone(tz).strftime("%d %B %Y at %I:%M %p %Z").lstrip("0")


async def send_caller_confirmation(
    caller_email: str,
    caller_name: str,
    business_name: str,
    action: str,
    appointment_dt: datetime | None,
    business_timezone: str,
) -> None:
    """Send appointment confirmation to the caller.

    Args:
        caller_email: Recipient email address.
        caller_name: Caller's name for personalisation.
        business_name: Name of the business.
        action: One of "booked", "rescheduled", "cancelled".
        appointment_dt: Scheduled datetime (None for cancellations).
        business_timezone: IANA timezone string, e.g. "America/New_York".
    """
    subject = f"Your appointment at {business_name} — {action}"

    dt_line = ""
    if action != "cancelled" and appointment_dt is not None:
        dt_line = f"Date and time: {_format_dt(appointment_dt, business_timezone)}\n\n"

    body = (
        f"Hi {caller_name},\n\n"
        f"Your appointment at {business_name} has been {action}.\n\n"
        f"{dt_line}"
        "If you have any questions, please call us directly.\n\n"
        "Thank you!"
    )
    await _send(caller_email, subject, body)


async def send_owner_alert(
    owner_email: str,
    business_name: str,
    action: str,
    caller_name: str,
    caller_phone: str,
    caller_email: str,
    appointment_dt: datetime | None,
    business_timezone: str,
) -> None:
    """Send appointment action alert to the business owner.

    Args:
        owner_email: Business owner's email address.
        business_name: Name of the business.
        action: One of "booked", "rescheduled", "cancelled".
        caller_name: Caller's full name.
        caller_phone: Caller's phone number.
        caller_email: Caller's email address.
        appointment_dt: Scheduled datetime (None when not relevant).
        business_timezone: IANA timezone string.
    """
    subject = f"[Voice Agent] Appointment {action} — {caller_name}"

    dt_line = ""
    if appointment_dt is not None:
        dt_line = f"Appointment time: {_format_dt(appointment_dt, business_timezone)}\n\n"

    body = (
        f"A caller has {action} an appointment.\n\n"
        "Caller details:\n"
        f"  Name:  {caller_name}\n"
        f"  Phone: {caller_phone}\n"
        f"  Email: {caller_email}\n\n"
        f"{dt_line}"
        f"Business: {business_name}"
    )
    await _send(owner_email, subject, body)


async def send_callback_request(
    owner_email: str,
    business_name: str,
    caller_name: str,
    caller_phone: str,
    reason: str,
) -> None:
    """Send callback request to the business owner when agent cannot help.

    Args:
        owner_email: Business owner's email address.
        business_name: Name of the business.
        caller_name: Caller's full name.
        caller_phone: Caller's phone number.
        reason: One of "no_slot_found", "cannot_understand", "caller_requested".
    """
    subject = f"[Voice Agent] Callback requested — {caller_name}"
    reason_label = _REASON_LABELS.get(reason, reason)

    body = (
        f"A caller needs a callback from {business_name}.\n\n"
        "Caller details:\n"
        f"  Name:  {caller_name}\n"
        f"  Phone: {caller_phone}\n\n"
        f"Reason: {reason_label}\n\n"
        "Please call them back at your earliest convenience."
    )
    await _send(owner_email, subject, body)
