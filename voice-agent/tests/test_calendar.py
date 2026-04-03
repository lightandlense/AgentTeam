"""Unit tests for app/services/calendar.py.

All external dependencies are mocked:
  - Google Calendar API (googleapiclient.discovery.build)
  - DB session (AsyncMock)
  - decrypt_token / encrypt_token
  - get_settings

No live database or real OAuth tokens required.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Environment setup — must happen before any app imports
# ---------------------------------------------------------------------------

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("RETELL_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-google-client-secret")

from app.services.calendar import (  # noqa: E402
    CalendarError,
    create_event,
    delete_event,
    get_free_slots,
    update_event,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_TZ = "America/Chicago"
_CLIENT_ID = "test-client"


def _make_settings():
    s = MagicMock()
    s.encryption_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    s.google_client_id = "test-client-id"
    s.google_client_secret = "test-client-secret"
    return s


def _make_token_row(expired: bool = False) -> MagicMock:
    row = MagicMock()
    row.id = 1
    row.client_id = _CLIENT_ID
    row.encrypted_access_token = "enc_access"
    row.encrypted_refresh_token = "enc_refresh"
    if expired:
        row.token_expiry = datetime(2020, 1, 1, tzinfo=timezone.utc)
    else:
        row.token_expiry = datetime(2099, 1, 1, tzinfo=timezone.utc)
    return row


def _make_client_row(working_days=None, lead_time_minutes=60) -> MagicMock:
    client = MagicMock()
    client.client_id = _CLIENT_ID
    client.timezone = _TZ
    client.working_days = working_days if working_days is not None else [1, 2, 3, 4, 5]
    client.business_hours = {"start": "09:00", "end": "17:00"}
    client.slot_duration_minutes = 60
    client.buffer_minutes = 0
    client.lead_time_minutes = lead_time_minutes
    return client


def _make_db(token_row=None, client_row=None) -> AsyncMock:
    """Return an AsyncMock DB that yields token_row for OAuthToken queries
    and client_row for Client queries."""
    db = AsyncMock()

    async def _execute(stmt):
        result = MagicMock()
        # Peek at the statement's froms to decide which row to return
        stmt_str = str(stmt)
        if "oauth_tokens" in stmt_str.lower():
            result.scalar_one_or_none.return_value = token_row
        elif "clients" in stmt_str.lower():
            result.scalar_one_or_none.return_value = client_row
        else:
            result.scalar_one_or_none.return_value = None
        return result

    db.execute.side_effect = _execute
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _make_service(freebusy_busy=None, event_response=None) -> MagicMock:
    """Return a mock Google Calendar Resource."""
    service = MagicMock()

    # freebusy
    fb_execute = MagicMock(
        return_value={
            "calendars": {"primary": {"busy": freebusy_busy or []}}
        }
    )
    service.freebusy.return_value.query.return_value.execute = fb_execute

    # events CRUD
    ev_resp = event_response or {"id": "evt_abc123"}
    service.events.return_value.insert.return_value.execute = MagicMock(return_value=ev_resp)
    service.events.return_value.patch.return_value.execute = MagicMock(return_value=ev_resp)
    service.events.return_value.delete.return_value.execute = MagicMock(return_value=None)

    return service


_PATCH_DECRYPT = "app.services.calendar.decrypt_token"
_PATCH_ENCRYPT = "app.services.calendar.encrypt_token"
_PATCH_SETTINGS = "app.services.calendar.get_settings"
_PATCH_BUILD = "app.services.calendar.googleapiclient.discovery.build"
_PATCH_CREDS = "app.services.calendar.google.oauth2.credentials.Credentials"


# ---------------------------------------------------------------------------
# Task 1 – get_free_slots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_free_slots_returns_slots_within_window():
    """Slots returned fall within window, on working days, inside business hours."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(_TZ)
    # Use a future Monday — one week from the next weekday to avoid hitting "now" clamping.
    # Find the next Monday from today (2026-04-03 is a Friday, so next Mon is 2026-04-06)
    # Use 2026-04-06 which is a Monday.
    window_start = datetime(2026, 4, 6, 14, 0, tzinfo=timezone.utc)  # 09:00 CDT
    window_end = datetime(2026, 4, 6, 22, 0, tzinfo=timezone.utc)   # 17:00 CDT

    client = _make_client_row(lead_time_minutes=0)
    token = _make_token_row()
    db = _make_db(token_row=token, client_row=client)
    service = _make_service(freebusy_busy=[])

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
    ):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        slots = await get_free_slots(db, _CLIENT_ID, window_start, window_end, max_slots=3)

    assert len(slots) > 0
    for slot in slots:
        assert slot.isoweekday() in [1, 2, 3, 4, 5]
        assert slot.hour >= 9
        assert slot.hour < 17


@pytest.mark.asyncio
async def test_get_free_slots_skips_busy_periods():
    """Slot overlapping a busy block is not returned."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(_TZ)
    # Monday 2026-04-06, 09:00 – 10:00 CDT is busy
    busy_start = datetime(2026, 4, 6, 9, 0, tzinfo=tz)
    busy_end = datetime(2026, 4, 6, 10, 0, tzinfo=tz)

    window_start = datetime(2026, 4, 6, 14, 0, tzinfo=timezone.utc)  # 09:00 CDT
    window_end = datetime(2026, 4, 6, 16, 0, tzinfo=timezone.utc)    # 11:00 CDT

    client = _make_client_row(lead_time_minutes=0)
    token = _make_token_row()
    db = _make_db(token_row=token, client_row=client)
    service = _make_service(
        freebusy_busy=[
            {"start": busy_start.isoformat(), "end": busy_end.isoformat()}
        ]
    )

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
    ):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        slots = await get_free_slots(db, _CLIENT_ID, window_start, window_end, max_slots=5)

    # The 09:00 CDT slot overlaps the busy block — should NOT appear
    for slot in slots:
        assert not (slot.hour == 9 and slot.minute == 0), "Busy slot was returned"


@pytest.mark.asyncio
async def test_get_free_slots_respects_lead_time():
    """No slot returned within lead_time_minutes of now."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(_TZ)
    # Use a window starting well in the past so all slots would be filtered by lead time
    now = datetime.now(tz)
    window_start = now - timedelta(hours=2)
    window_end = now + timedelta(minutes=30)  # only 30 min ahead — less than 120 min lead time

    client = _make_client_row(lead_time_minutes=120)
    token = _make_token_row()
    db = _make_db(token_row=token, client_row=client)
    service = _make_service(freebusy_busy=[])

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
    ):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        slots = await get_free_slots(db, _CLIENT_ID, window_start, window_end, max_slots=5)

    # Window end is 30 min from now, lead_time is 120 min — no slot should be within window
    for slot in slots:
        assert slot >= now + timedelta(minutes=120), "Slot violates lead_time_minutes"


@pytest.mark.asyncio
async def test_get_free_slots_skips_non_working_days():
    """No Saturday or Sunday slots returned when working_days=[1,2,3,4,5]."""
    # Saturday 2026-04-11 and Sunday 2026-04-12
    window_start = datetime(2026, 4, 11, 14, 0, tzinfo=timezone.utc)  # 09:00 CDT Sat
    window_end = datetime(2026, 4, 12, 22, 0, tzinfo=timezone.utc)    # 17:00 CDT Sun

    client = _make_client_row(working_days=[1, 2, 3, 4, 5], lead_time_minutes=0)
    token = _make_token_row()
    db = _make_db(token_row=token, client_row=client)
    service = _make_service(freebusy_busy=[])

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
    ):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        slots = await get_free_slots(db, _CLIENT_ID, window_start, window_end, max_slots=5)

    assert slots == [], f"Expected no slots on weekend, got {slots}"


@pytest.mark.asyncio
async def test_get_free_slots_returns_empty_when_no_slots():
    """Returns empty list (not CalendarError) when entire window is busy."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(_TZ)
    window_start = datetime(2026, 4, 6, 14, 0, tzinfo=timezone.utc)  # 09:00 CDT Mon
    window_end = datetime(2026, 4, 6, 22, 0, tzinfo=timezone.utc)    # 17:00 CDT Mon

    # Mark the whole day as busy
    busy = [
        {
            "start": datetime(2026, 4, 6, 9, 0, tzinfo=tz).isoformat(),
            "end": datetime(2026, 4, 6, 17, 0, tzinfo=tz).isoformat(),
        }
    ]

    client = _make_client_row(lead_time_minutes=0)
    token = _make_token_row()
    db = _make_db(token_row=token, client_row=client)
    service = _make_service(freebusy_busy=busy)

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
    ):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        slots = await get_free_slots(db, _CLIENT_ID, window_start, window_end, max_slots=3)

    assert slots == []


# ---------------------------------------------------------------------------
# Task 2 – create_event / update_event / delete_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_event_returns_event_id():
    """create_event returns the event ID from the API response."""
    start = datetime(2024, 4, 8, 15, 0, tzinfo=timezone.utc)
    end = datetime(2024, 4, 8, 16, 0, tzinfo=timezone.utc)

    token = _make_token_row()
    client = _make_client_row()
    db = _make_db(token_row=token, client_row=client)
    service = _make_service(event_response={"id": "abc123"})

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
    ):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        event_id = await create_event(
            db, _CLIENT_ID, start, end, "Appointment", "Notes here"
        )

    assert event_id == "abc123"


@pytest.mark.asyncio
async def test_update_event_returns_event_id():
    """update_event returns the patched event ID from the API response."""
    new_start = datetime(2024, 4, 9, 15, 0, tzinfo=timezone.utc)
    new_end = datetime(2024, 4, 9, 16, 0, tzinfo=timezone.utc)

    token = _make_token_row()
    client = _make_client_row()
    db = _make_db(token_row=token, client_row=client)
    service = _make_service(event_response={"id": "abc123"})

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
    ):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        event_id = await update_event(db, _CLIENT_ID, "abc123", new_start, new_end)

    assert event_id == "abc123"


@pytest.mark.asyncio
async def test_delete_event_calls_api():
    """delete_event returns None and calls the Google delete API with correct eventId."""
    token = _make_token_row()
    client = _make_client_row()
    db = _make_db(token_row=token, client_row=client)
    service = _make_service()

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
    ):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        result = await delete_event(db, _CLIENT_ID, "evt_to_delete")

    assert result is None
    service.events.return_value.delete.assert_called_once_with(
        calendarId="primary", eventId="evt_to_delete"
    )


@pytest.mark.asyncio
async def test_calendar_error_on_api_failure():
    """HttpError from events().insert().execute() raises CalendarError, not HttpError."""
    from googleapiclient.errors import HttpError
    from httplib2 import Response as HttpLib2Response

    start = datetime(2024, 4, 8, 15, 0, tzinfo=timezone.utc)
    end = datetime(2024, 4, 8, 16, 0, tzinfo=timezone.utc)

    token = _make_token_row()
    client = _make_client_row()
    db = _make_db(token_row=token, client_row=client)
    service = MagicMock()
    http_error = HttpError(
        resp=HttpLib2Response({"status": "403"}), content=b"Forbidden"
    )
    service.events.return_value.insert.return_value.execute.side_effect = http_error

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
    ):
        mock_creds = MagicMock()
        mock_creds.expired = False
        mock_creds.refresh_token = None
        mock_creds_cls.return_value = mock_creds

        with pytest.raises(CalendarError):
            await create_event(db, _CLIENT_ID, start, end, "Test", "Test desc")


@pytest.mark.asyncio
async def test_token_refresh_updates_db():
    """When credentials.expired=True and refresh_token set, OAuthToken row is updated."""
    token = _make_token_row(expired=True)
    client = _make_client_row()
    db = _make_db(token_row=token, client_row=client)
    service = _make_service(event_response={"id": "refreshed_evt"})

    new_access_token = "new_access_token_value"

    with (
        patch(_PATCH_DECRYPT, return_value="plain_token"),
        patch(_PATCH_ENCRYPT, return_value="new_enc_access") as mock_encrypt,
        patch(_PATCH_SETTINGS, return_value=_make_settings()),
        patch(_PATCH_BUILD, return_value=service),
        patch(_PATCH_CREDS) as mock_creds_cls,
        patch("app.services.calendar.google.auth.transport.requests.Request"),
    ):
        mock_creds = MagicMock()
        mock_creds.expired = True
        mock_creds.refresh_token = "enc_refresh"
        mock_creds.token = new_access_token
        mock_creds.expiry = datetime(2099, 1, 1, tzinfo=timezone.utc)

        def _refresh(_request):
            mock_creds.expired = False

        mock_creds.refresh.side_effect = _refresh
        mock_creds_cls.return_value = mock_creds

        start = datetime(2024, 4, 8, 15, 0, tzinfo=timezone.utc)
        end = datetime(2024, 4, 8, 16, 0, tzinfo=timezone.utc)
        await create_event(db, _CLIENT_ID, start, end, "Meeting", "")

    # Verify encrypt_token was called with the new access token
    mock_encrypt.assert_called_once_with(new_access_token, _make_settings().encryption_key)
    # Verify db.add was called to persist the updated token row
    db.add.assert_called()
    db.flush.assert_called()
