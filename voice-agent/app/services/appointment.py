"""Appointment orchestration service.

Owns the appointment lifecycle business logic: booking with 6-field intake
validation, alternative slot offering, window-based slot search, and
reschedule/cancel operations. Callers into this service never touch the
Google Calendar API directly — all calendar interaction is delegated to
app.services.calendar.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Appointment, Client
from app.services.calendar import (
    CalendarError,
    create_event,
    delete_event,
    get_free_slots,
    update_event,
)
from app.services.calendar import get_calendar_service as _get_calendar_service

logger = logging.getLogger(__name__)

__all__ = [
    "AppointmentError",
    "BookingRequest",
    "BookingResult",
    "AppointmentMatch",
    "book_appointment",
    "find_slot_in_window",
    "find_appointment",
    "find_appointment_by_phone",
    "reschedule_appointment",
    "cancel_appointment",
]

_MAX_WINDOW_DAYS = 30


def _normalize_phone(phone: str) -> str:
    """Strip all non-digit characters for consistent phone matching."""
    import re
    digits = re.sub(r"\D", "", phone)
    # Drop leading country code '1' for US numbers (11 digits → 10)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


class AppointmentError(Exception):
    """Caller-safe exception for appointment lifecycle failures.

    Wraps CalendarError internally. Message is safe to relay to phone callers.
    """


@dataclass(frozen=True)
class BookingRequest:
    """All 6 required fields for a new appointment."""

    name: str
    phone: str
    email: str
    address: str
    problem_description: str
    access_notes: str


@dataclass(frozen=True)
class BookingResult:
    """Result returned by book_appointment."""

    confirmed: bool
    event_id: str | None
    slot: datetime | None
    alternatives: list[datetime] = field(default_factory=list)


@dataclass(frozen=True)
class AppointmentMatch:
    """A single calendar event that matched a lookup query."""

    event_id: str
    summary: str
    start: datetime
    end: datetime


def _build_description(req: BookingRequest) -> str:
    """Build a newline-separated event description from all 6 booking fields."""
    return (
        f"Name: {req.name}\n"
        f"Phone: {req.phone}\n"
        f"Email: {req.email}\n"
        f"Address: {req.address}\n"
        f"Problem: {req.problem_description}\n"
        f"Access notes: {req.access_notes}"
    )


async def book_appointment(
    db: AsyncSession,
    client_id: str,
    requested_slot: datetime,
    booking_request: BookingRequest,
) -> BookingResult:
    """Book an appointment at requested_slot, or offer up to 2 alternatives.

    Returns a BookingResult with confirmed=True when the slot is free and the
    event has been created. Returns confirmed=False with up to 2 alternative
    slots when the requested slot is busy.

    Raises AppointmentError on unrecoverable calendar failures.
    """
    try:
        # Use UTC-aware now so it compares cleanly with tz-aware slots from get_free_slots
        now = datetime.now(timezone.utc)
        if requested_slot.tzinfo is None:
            requested_slot = requested_slot.replace(tzinfo=timezone.utc)
        # Reject past slots — find alternatives from now instead
        if requested_slot < now:
            alt_end = now + timedelta(days=7)
            alternatives = await get_free_slots(db, client_id, now, alt_end, max_slots=2)
            return BookingResult(confirmed=False, event_id=None, slot=None, alternatives=alternatives)

        # Check if the exact slot is free using freebusy API directly
        result = await db.execute(select(Client).where(Client.client_id == client_id))
        client = result.scalar_one_or_none()
        slot_minutes = client.slot_duration_minutes if client else 60
        slot_end = requested_slot + timedelta(minutes=slot_minutes)
        service = await _get_calendar_service(db, client_id)
        fb = service.freebusy().query(body={
            "timeMin": requested_slot.isoformat(),
            "timeMax": slot_end.isoformat(),
            "items": [{"id": "primary"}],
        }).execute()
        busy = fb.get("calendars", {}).get("primary", {}).get("busy", [])
        slot_is_free = not any(
            requested_slot < datetime.fromisoformat(p["end"].replace("Z", "+00:00"))
            and slot_end > datetime.fromisoformat(p["start"].replace("Z", "+00:00"))
            for p in busy
        )

        if slot_is_free:
            description = _build_description(booking_request)
            end_dt = slot_end

            summary = booking_request.name
            if booking_request.problem_description:
                summary = f"{booking_request.name} – {booking_request.problem_description}"
            event_id = await create_event(
                db,
                client_id,
                requested_slot,
                end_dt,
                summary=summary,
                description=description,
                attendee_email=booking_request.email,
            )
            db.add(Appointment(
                client_id=client_id,
                event_id=event_id,
                caller_phone=_normalize_phone(booking_request.phone),
                caller_name=booking_request.name,
                caller_email=booking_request.email,
                slot_dt=requested_slot,
                status="active",
            ))
            await db.commit()
            return BookingResult(
                confirmed=True,
                event_id=event_id,
                slot=requested_slot,
                alternatives=[],
            )

        # Slot is busy — fetch up to 2 alternatives in the next 30 days
        alt_end = requested_slot + timedelta(days=_MAX_WINDOW_DAYS)
        alternatives = await get_free_slots(db, client_id, requested_slot, alt_end, max_slots=2)
        return BookingResult(
            confirmed=False,
            event_id=None,
            slot=None,
            alternatives=alternatives,
        )

    except CalendarError as exc:
        logger.error("CalendarError in book_appointment for %s: %s", client_id, exc)
        raise AppointmentError("I'm having trouble accessing the calendar right now") from exc


async def find_slot_in_window(
    db: AsyncSession,
    client_id: str,
    window_start: datetime,
    window_end: datetime,
) -> list[datetime]:
    """Return up to 3 free slots within the given window (capped at 30 days).

    Returns an empty list when no slots are found — the caller should transfer
    to a human team member in that case.

    Raises AppointmentError on unrecoverable calendar failures.
    """
    try:
        capped_end = min(window_end, window_start + timedelta(days=_MAX_WINDOW_DAYS))
        return await get_free_slots(db, client_id, window_start, capped_end, max_slots=3)
    except CalendarError as exc:
        logger.error("CalendarError in find_slot_in_window for %s: %s", client_id, exc)
        raise AppointmentError("I'm having trouble accessing the calendar right now") from exc


async def find_appointment_by_phone(
    db: AsyncSession,
    client_id: str,
    caller_phone: str,
) -> list[AppointmentMatch]:
    """Look up active appointments in Postgres by caller phone number.

    Returns all active appointments for this caller across any date, ordered
    soonest first. This is the preferred lookup — no name ambiguity, no
    calendar API call required.
    """
    try:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Appointment)
            .where(
                Appointment.client_id == client_id,
                Appointment.caller_phone == _normalize_phone(caller_phone),
                Appointment.status == "active",
                Appointment.slot_dt >= now,
            )
            .order_by(Appointment.slot_dt)
        )
        rows = result.scalars().all()
        return [
            AppointmentMatch(
                event_id=row.event_id,
                summary=row.caller_name,
                start=row.slot_dt,
                end=row.slot_dt,
            )
            for row in rows
        ]
    except Exception as exc:
        logger.error("Error in find_appointment_by_phone for %s: %s", client_id, exc)
        raise AppointmentError("I'm having trouble looking up your appointment right now") from exc


async def find_appointment(
    db: AsyncSession,
    client_id: str,
    caller_name: str,
    appointment_date: datetime,
) -> list[AppointmentMatch]:
    """Look up Google Calendar events by caller name and date.

    Searches the full day (00:00–23:59) in the client's timezone. Filters
    events by case-insensitive name match. Returns all matching events —
    may be empty or multiple.

    Raises AppointmentError on unrecoverable calendar failures.
    """
    try:
        result = await db.execute(select(Client).where(Client.client_id == client_id))
        client = result.scalar_one_or_none()
        tz = ZoneInfo(client.timezone if client else "UTC")

        day_start = appointment_date.replace(hour=0, minute=0, second=0, microsecond=0)
        if day_start.tzinfo is None:
            day_start = day_start.replace(tzinfo=tz)
        else:
            day_start = day_start.astimezone(tz).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        day_end = day_start.replace(hour=23, minute=59, second=59)

        service = await _get_calendar_service(db, client_id)
        response = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=day_start.isoformat(),
                timeMax=day_end.isoformat(),
                q=caller_name,
            )
            .execute()
        )

        items = response.get("items", [])
        matches: list[AppointmentMatch] = []
        lower_name = caller_name.lower()

        for item in items:
            summary = item.get("summary", "")
            if lower_name not in summary.lower():
                continue

            raw_start = item.get("start", {}).get("dateTime", "")
            raw_end = item.get("end", {}).get("dateTime", "")
            if not raw_start or not raw_end:
                continue

            matches.append(
                AppointmentMatch(
                    event_id=item["id"],
                    summary=summary,
                    start=datetime.fromisoformat(raw_start),
                    end=datetime.fromisoformat(raw_end),
                )
            )

        return matches

    except CalendarError as exc:
        logger.error("CalendarError in find_appointment for %s: %s", client_id, exc)
        raise AppointmentError("I'm having trouble accessing the calendar right now") from exc
    except AppointmentError:
        raise
    except Exception as exc:
        logger.error("Unexpected error in find_appointment for %s: %s", client_id, exc)
        raise AppointmentError("I'm having trouble accessing the calendar right now") from exc


async def reschedule_appointment(
    db: AsyncSession,
    client_id: str,
    event_id: str,
    new_start_dt: datetime,
    slot_duration_minutes: int,
) -> str:
    """Move an existing appointment to a new start time.

    Computes new_end_dt from slot_duration_minutes, patches the calendar event,
    and returns the event_id.

    Raises AppointmentError on unrecoverable calendar failures.
    """
    try:
        new_end_dt = new_start_dt + timedelta(minutes=slot_duration_minutes)
        updated_event_id = await update_event(db, client_id, event_id, new_start_dt, new_end_dt)
        result = await db.execute(
            select(Appointment).where(
                Appointment.client_id == client_id,
                Appointment.event_id == event_id,
            )
        )
        appt = result.scalar_one_or_none()
        if appt is not None:
            appt.slot_dt = new_start_dt
            appt.updated_at = func.now()
            await db.commit()
        return updated_event_id
    except CalendarError as exc:
        logger.error("CalendarError in reschedule_appointment for %s: %s", client_id, exc)
        raise AppointmentError("I'm having trouble accessing the calendar right now") from exc


async def cancel_appointment(
    db: AsyncSession,
    client_id: str,
    event_id: str,
) -> None:
    """Delete an appointment from Google Calendar.

    Raises AppointmentError on unrecoverable calendar failures.
    """
    try:
        await delete_event(db, client_id, event_id)
        result = await db.execute(
            select(Appointment).where(
                Appointment.client_id == client_id,
                Appointment.event_id == event_id,
            )
        )
        appt = result.scalar_one_or_none()
        if appt is not None:
            appt.status = "cancelled"
            appt.updated_at = func.now()
            await db.commit()
    except CalendarError as exc:
        logger.error("CalendarError in cancel_appointment for %s: %s", client_id, exc)
        raise AppointmentError("I'm having trouble accessing the calendar right now") from exc
