"""Google Calendar service layer.

Provides OAuth token loading/refresh, free slot computation, and CRUD
operations on Google Calendar events. This is the only module that talks
directly to the Google Calendar API.
"""

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import google.auth.transport.requests
import google.oauth2.credentials
import googleapiclient.discovery
from googleapiclient.errors import HttpError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.client import Client, OAuthToken
from app.services.encryption import decrypt_token, encrypt_token

logger = logging.getLogger(__name__)

__all__ = [
    "CalendarError",
    "get_free_slots",
    "create_event",
    "update_event",
    "delete_event",
]

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarError(Exception):
    """Raised for all Google Calendar API failures. Message is safe to relay to callers."""


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


async def get_calendar_service(db: AsyncSession, client_id: str):  # noqa: ANN201
    """Load OAuth tokens for client_id, refresh if expired, return a Calendar Resource."""
    try:
        result = await db.execute(
            select(OAuthToken)
            .where(OAuthToken.client_id == client_id)
            .order_by(OAuthToken.id.desc())
            .limit(1)
        )
        token_row = result.scalar_one_or_none()
        if token_row is None:
            raise CalendarError("No OAuth token found for this client.")

        settings = get_settings()
        access_token = decrypt_token(token_row.encrypted_access_token, settings.encryption_key)
        refresh_token = decrypt_token(token_row.encrypted_refresh_token, settings.encryption_key)

        expiry = token_row.token_expiry
        if expiry is not None and expiry.tzinfo is not None:
            expiry = expiry.replace(tzinfo=None)

        credentials = google.oauth2.credentials.Credentials(
            token=access_token,
            refresh_token=refresh_token,
            expiry=expiry,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=_SCOPES,
        )

        if credentials.expired and credentials.refresh_token:
            credentials.refresh(google.auth.transport.requests.Request())
            new_encrypted = encrypt_token(credentials.token, settings.encryption_key)
            token_row.encrypted_access_token = new_encrypted
            token_row.token_expiry = credentials.expiry
            await db.execute(
                select(OAuthToken).where(OAuthToken.id == token_row.id)
            )
            db.add(token_row)
            await db.flush()

        return googleapiclient.discovery.build(
            "calendar", "v3", credentials=credentials, cache_discovery=False
        )
    except CalendarError:
        raise
    except Exception as exc:
        logger.error("Failed to build calendar service for client %s: %s", client_id, exc)
        raise CalendarError("Calendar service unavailable. Please try again later.") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_free_slots(
    db: AsyncSession,
    client_id: str,
    window_start: datetime,
    window_end: datetime,
    max_slots: int = 3,
) -> list[datetime]:
    """Return up to max_slots free datetime slots within the given window.

    Respects working_days, business_hours, slot_duration_minutes,
    buffer_minutes, and lead_time_minutes from the Client row.
    """
    try:
        result = await db.execute(
            select(Client).where(Client.client_id == client_id)
        )
        client = result.scalar_one_or_none()
        if client is None:
            raise CalendarError("Client not found.")

        tz = ZoneInfo(client.timezone)
        now = datetime.now(tz)

        bh_start = time.fromisoformat(client.business_hours["start"])
        bh_end = time.fromisoformat(client.business_hours["end"])
        slot_delta = timedelta(minutes=client.slot_duration_minutes)
        step_delta = timedelta(minutes=client.slot_duration_minutes + client.buffer_minutes)
        earliest = now + timedelta(minutes=client.lead_time_minutes)

        # Clamp window_start to earliest allowed
        effective_start = max(
            window_start.astimezone(tz) if window_start.tzinfo else window_start.replace(tzinfo=tz),
            earliest,
        )
        effective_end = (
            window_end.astimezone(tz) if window_end.tzinfo else window_end.replace(tzinfo=tz)
        )

        service = await get_calendar_service(db, client_id)
        freebusy_response = (
            service.freebusy()
            .query(
                body={
                    "timeMin": effective_start.isoformat(),
                    "timeMax": effective_end.isoformat(),
                    "items": [{"id": "primary"}],
                }
            )
            .execute()
        )
        busy_periods = freebusy_response.get("calendars", {}).get("primary", {}).get("busy", [])

        def _is_busy(slot_s: datetime, slot_e: datetime) -> bool:
            for period in busy_periods:
                p_start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
                p_end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
                if slot_s < p_end and slot_e > p_start:
                    return True
            return False

        slots: list[datetime] = []
        current_date = effective_start.date()

        while current_date <= effective_end.date() and len(slots) < max_slots:
            if current_date.isoweekday() not in client.working_days:
                current_date += timedelta(days=1)
                continue

            day_start = datetime.combine(current_date, bh_start, tzinfo=tz)
            day_end = datetime.combine(current_date, bh_end, tzinfo=tz)

            slot_s = day_start
            while slot_s < day_end and len(slots) < max_slots:
                slot_e = slot_s + slot_delta
                if slot_e > day_end:
                    break
                if slot_s < effective_start:
                    slot_s += step_delta
                    continue
                if slot_s > effective_end:
                    break
                if not _is_busy(slot_s, slot_e):
                    slots.append(slot_s)
                slot_s += step_delta

            current_date += timedelta(days=1)

        return slots
    except CalendarError:
        raise
    except HttpError as exc:
        logger.error("Google API error in get_free_slots for %s: %s", client_id, exc)
        raise CalendarError("Failed to retrieve calendar availability.") from exc
    except Exception as exc:
        logger.error("Unexpected error in get_free_slots for %s: %s", client_id, exc)
        raise CalendarError("Failed to retrieve calendar availability.") from exc


async def create_event(
    db: AsyncSession,
    client_id: str,
    start_dt: datetime,
    end_dt: datetime,
    summary: str,
    description: str,
) -> str:
    """Create a Google Calendar event and return the event ID."""
    try:
        result = await db.execute(select(Client).where(Client.client_id == client_id))
        client = result.scalar_one_or_none()
        tz_name = client.timezone if client else "UTC"

        service = await get_calendar_service(db, client_id)
        event_body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": tz_name},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz_name},
        }
        event = service.events().insert(calendarId="primary", body=event_body).execute()
        return event["id"]
    except CalendarError:
        raise
    except HttpError as exc:
        logger.error("Google API error in create_event for %s: %s", client_id, exc)
        raise CalendarError("Failed to create calendar event.") from exc
    except Exception as exc:
        logger.error("Unexpected error in create_event for %s: %s", client_id, exc)
        raise CalendarError("Failed to create calendar event.") from exc


async def update_event(
    db: AsyncSession,
    client_id: str,
    event_id: str,
    new_start_dt: datetime,
    new_end_dt: datetime,
) -> str:
    """Patch an existing event's start/end time and return the updated event ID."""
    try:
        result = await db.execute(select(Client).where(Client.client_id == client_id))
        client = result.scalar_one_or_none()
        tz_name = client.timezone if client else "UTC"

        service = await get_calendar_service(db, client_id)
        patch_body = {
            "start": {"dateTime": new_start_dt.isoformat(), "timeZone": tz_name},
            "end": {"dateTime": new_end_dt.isoformat(), "timeZone": tz_name},
        }
        event = (
            service.events()
            .patch(calendarId="primary", eventId=event_id, body=patch_body)
            .execute()
        )
        return event["id"]
    except CalendarError:
        raise
    except HttpError as exc:
        logger.error("Google API error in update_event for %s: %s", client_id, exc)
        raise CalendarError("Failed to update calendar event.") from exc
    except Exception as exc:
        logger.error("Unexpected error in update_event for %s: %s", client_id, exc)
        raise CalendarError("Failed to update calendar event.") from exc


async def delete_event(
    db: AsyncSession,
    client_id: str,
    event_id: str,
) -> None:
    """Remove an event by event ID."""
    try:
        service = await get_calendar_service(db, client_id)
        service.events().delete(calendarId="primary", eventId=event_id).execute()
    except CalendarError:
        raise
    except HttpError as exc:
        logger.error("Google API error in delete_event for %s: %s", client_id, exc)
        raise CalendarError("Failed to delete calendar event.") from exc
    except Exception as exc:
        logger.error("Unexpected error in delete_event for %s: %s", client_id, exc)
        raise CalendarError("Failed to delete calendar event.") from exc
