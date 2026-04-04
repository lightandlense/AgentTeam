"""Async email notification service.

Provides three public functions for sending appointment-related emails.
All functions are fire-and-forget safe: exceptions are caught and logged,
never raised. The webhook response is never blocked by email failures.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from app.config import get_settings

__all__ = ["send_caller_confirmation", "send_owner_alert", "send_callback_request"]

logger = logging.getLogger(__name__)

_REASON_LABELS: dict[str, str] = {
    "no_slot_found": "No available appointment slots could be found",
    "cannot_understand": "Agent was unable to understand the caller after multiple attempts",
    "caller_requested": "Caller explicitly requested to speak with someone",
}


async def _send(to_address: str, subject: str, body: str) -> None:
    """Internal helper: send a plain-text email via SendGrid HTTP API."""
    settings = get_settings()
    if not settings.smtp_password:
        logger.debug("SendGrid API key not configured; skipping email to %s", to_address)
        return
    if not to_address:
        logger.debug("No recipient address; skipping email")
        return
    try:
        message = Mail(
            from_email=settings.smtp_from_address,
            to_emails=to_address,
            subject=subject,
            plain_text_content=body,
        )
        sg = SendGridAPIClient(settings.smtp_password)
        response = sg.send(message)
        logger.info("Email sent to %s: %s (status %s)", to_address, subject, response.status_code)
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
    """Send appointment confirmation to the caller."""
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
    caller_address: str = "",
    problem_description: str = "",
) -> None:
    """Send appointment action alert to the business owner."""
    subject = f"[Voice Agent] Appointment {action} — {caller_name}"

    dt_line = ""
    if appointment_dt is not None:
        dt_line = f"Appointment time: {_format_dt(appointment_dt, business_timezone)}\n\n"

    address_line = f"  Address: {caller_address}\n" if caller_address else ""
    problem_line = f"\nIssue: {problem_description}\n" if problem_description else ""

    body = (
        f"A caller has {action} an appointment.\n\n"
        "Caller details:\n"
        f"  Name:  {caller_name}\n"
        f"  Phone: {caller_phone}\n"
        f"  Email: {caller_email}\n"
        f"{address_line}"
        f"{problem_line}\n"
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
    """Send callback request to the business owner when agent cannot help."""
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
