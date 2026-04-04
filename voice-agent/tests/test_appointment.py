"""Unit tests for app/services/appointment.py.

All calendar service functions are mocked so no live API calls are required.
Mocked targets:
  - app.services.appointment.get_free_slots
  - app.services.appointment.create_event
  - app.services.appointment.update_event
  - app.services.appointment.delete_event
  - app.services.appointment._get_calendar_service
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

from app.services.appointment import (  # noqa: E402
    AppointmentError,
    AppointmentMatch,
    BookingRequest,
    BookingResult,
    book_appointment,
    cancel_appointment,
    find_appointment,
    find_slot_in_window,
    reschedule_appointment,
)
from app.services.calendar import CalendarError  # noqa: E402

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_PATCH_GET_FREE_SLOTS = "app.services.appointment.get_free_slots"
_PATCH_CREATE_EVENT = "app.services.appointment.create_event"
_PATCH_UPDATE_EVENT = "app.services.appointment.update_event"
_PATCH_DELETE_EVENT = "app.services.appointment.delete_event"
_PATCH_GET_CAL_SVC = "app.services.appointment._get_calendar_service"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CLIENT_ID = "test-client"
_SLOT = datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc)
_ALT1 = datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc)
_ALT2 = datetime(2026, 5, 10, 11, 0, tzinfo=timezone.utc)


def _booking_request(**overrides) -> BookingRequest:
    defaults = dict(
        name="Alice Smith",
        phone="555-1234",
        email="alice@example.com",
        address="123 Main St",
        problem_description="Leaky faucet",
        access_notes="Side gate code 1234",
    )
    defaults.update(overrides)
    return BookingRequest(**defaults)


def _make_db_with_client(slot_duration_minutes: int = 60) -> AsyncMock:
    """Return an AsyncMock DB that yields a mock Client row."""
    db = AsyncMock()
    client = MagicMock()
    client.client_id = _CLIENT_ID
    client.timezone = "America/Chicago"
    client.slot_duration_minutes = slot_duration_minutes

    result = MagicMock()
    result.scalar_one_or_none.return_value = client
    db.execute = AsyncMock(return_value=result)
    return db


def _make_db_no_client() -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


# ---------------------------------------------------------------------------
# Task 1 — book_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_book_appointment_confirms_free_slot():
    """When exact slot is free, event is created and BookingResult is confirmed."""
    db = _make_db_with_client()

    with (
        patch(_PATCH_GET_FREE_SLOTS, new_callable=AsyncMock) as mock_slots,
        patch(_PATCH_CREATE_EVENT, new_callable=AsyncMock) as mock_create,
    ):
        mock_slots.return_value = [_SLOT]
        mock_create.return_value = "evt1"

        result = await book_appointment(db, _CLIENT_ID, _SLOT, _booking_request())

    assert result == BookingResult(confirmed=True, event_id="evt1", slot=_SLOT, alternatives=[])
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_book_appointment_offers_alternatives_when_busy():
    """When exact slot is busy, returns up to 2 alternative slots."""
    db = _make_db_with_client()

    async def _slots_side_effect(db, client_id, start, end, max_slots=3):
        # First call (max_slots=1) returns empty = slot is busy
        if max_slots == 1:
            return []
        # Second call (max_slots=2) returns alternatives
        return [_ALT1, _ALT2]

    with patch(_PATCH_GET_FREE_SLOTS, side_effect=_slots_side_effect):
        result = await book_appointment(db, _CLIENT_ID, _SLOT, _booking_request())

    assert result.confirmed is False
    assert result.event_id is None
    assert result.slot is None
    assert result.alternatives == [_ALT1, _ALT2]


@pytest.mark.asyncio
async def test_book_appointment_event_description_contains_all_fields():
    """create_event description includes all 6 booking fields."""
    db = _make_db_with_client()
    req = _booking_request(
        name="Bob Jones",
        phone="555-9999",
        email="bob@example.com",
        address="99 Oak Ave",
        problem_description="Broken heater",
        access_notes="No gate",
    )

    with (
        patch(_PATCH_GET_FREE_SLOTS, new_callable=AsyncMock, return_value=[_SLOT]),
        patch(_PATCH_CREATE_EVENT, new_callable=AsyncMock, return_value="evt2") as mock_create,
    ):
        await book_appointment(db, _CLIENT_ID, _SLOT, req)

    _, kwargs = mock_create.call_args
    description = kwargs.get("description", "") or mock_create.call_args[0][5]

    assert "Bob Jones" in description
    assert "555-9999" in description
    assert "bob@example.com" in description
    assert "99 Oak Ave" in description
    assert "Broken heater" in description
    assert "No gate" in description


@pytest.mark.asyncio
async def test_book_appointment_raises_on_calendar_error():
    """CalendarError from get_free_slots is wrapped in AppointmentError."""
    db = _make_db_with_client()

    with (
        patch(_PATCH_GET_FREE_SLOTS, new_callable=AsyncMock, side_effect=CalendarError("fail")),
        pytest.raises(AppointmentError),
    ):
        await book_appointment(db, _CLIENT_ID, _SLOT, _booking_request())


# ---------------------------------------------------------------------------
# Task 2 — find_slot_in_window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_slot_in_window_caps_at_30_days():
    """Window end is clamped to 30 days from window_start."""
    db = AsyncMock()
    window_start = _SLOT
    window_end = _SLOT + timedelta(days=60)  # beyond 30-day cap

    with patch(_PATCH_GET_FREE_SLOTS, new_callable=AsyncMock, return_value=[]) as mock_slots:
        await find_slot_in_window(db, _CLIENT_ID, window_start, window_end)

    # get_free_slots(db, client_id, window_start, capped_end, max_slots=3)
    # max_slots is a keyword arg, so call_args[0] has 4 positional items
    args = mock_slots.call_args[0]
    called_end = args[3]
    assert called_end <= window_start + timedelta(days=30), (
        f"Expected end <= 30 days, got {called_end}"
    )


@pytest.mark.asyncio
async def test_find_slot_in_window_returns_empty_list():
    """Returns [] when no free slots exist — caller should transfer."""
    db = AsyncMock()

    with patch(_PATCH_GET_FREE_SLOTS, new_callable=AsyncMock, return_value=[]):
        result = await find_slot_in_window(db, _CLIENT_ID, _SLOT, _SLOT + timedelta(days=7))

    assert result == []


# ---------------------------------------------------------------------------
# Task 3 — find_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_appointment_returns_matches():
    """Events matching caller_name are returned as AppointmentMatch objects."""
    db = _make_db_with_client()
    start_iso = "2026-05-10T09:00:00+00:00"
    end_iso = "2026-05-10T10:00:00+00:00"

    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt_a",
                "summary": "Alice Smith - appointment",
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
            },
            {
                "id": "evt_b",
                "summary": "Alice Smith - follow-up",
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
            },
        ]
    }

    with patch(_PATCH_GET_CAL_SVC, new_callable=AsyncMock, return_value=mock_service):
        matches = await find_appointment(db, _CLIENT_ID, "Alice Smith", _SLOT)

    assert len(matches) == 2
    assert all(isinstance(m, AppointmentMatch) for m in matches)
    assert matches[0].event_id == "evt_a"
    assert matches[1].event_id == "evt_b"


@pytest.mark.asyncio
async def test_find_appointment_returns_empty_for_no_match():
    """Events with different names are filtered out; empty list returned."""
    db = _make_db_with_client()
    start_iso = "2026-05-10T09:00:00+00:00"
    end_iso = "2026-05-10T10:00:00+00:00"

    mock_service = MagicMock()
    mock_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "evt_x",
                "summary": "Bob Jones - appointment",
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
            },
        ]
    }

    with patch(_PATCH_GET_CAL_SVC, new_callable=AsyncMock, return_value=mock_service):
        matches = await find_appointment(db, _CLIENT_ID, "Alice Smith", _SLOT)

    assert matches == []


# ---------------------------------------------------------------------------
# Task 4 — reschedule_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reschedule_appointment_calls_update_event():
    """reschedule_appointment calls update_event with correct start/end and returns event_id."""
    db = _make_db_no_client()
    new_start = datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)
    duration = 90

    with patch(_PATCH_UPDATE_EVENT, new_callable=AsyncMock, return_value="evt1") as mock_update:
        result = await reschedule_appointment(db, _CLIENT_ID, "evt1", new_start, duration)

    assert result == "evt1"
    expected_end = new_start + timedelta(minutes=duration)
    mock_update.assert_awaited_once_with(db, _CLIENT_ID, "evt1", new_start, expected_end)


# ---------------------------------------------------------------------------
# Task 5 — cancel_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_appointment_calls_delete_event():
    """cancel_appointment delegates to delete_event and returns None."""
    db = _make_db_no_client()

    with patch(_PATCH_DELETE_EVENT, new_callable=AsyncMock) as mock_delete:
        result = await cancel_appointment(db, _CLIENT_ID, "evt_del")

    assert result is None
    mock_delete.assert_awaited_once_with(db, _CLIENT_ID, "evt_del")


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reschedule_raises_on_calendar_error():
    """CalendarError from update_event is wrapped in AppointmentError."""
    db = AsyncMock()

    with (
        patch(_PATCH_UPDATE_EVENT, new_callable=AsyncMock, side_effect=CalendarError("err")),
        pytest.raises(AppointmentError),
    ):
        await reschedule_appointment(db, _CLIENT_ID, "evt1", _SLOT, 60)


@pytest.mark.asyncio
async def test_cancel_raises_on_calendar_error():
    """CalendarError from delete_event is wrapped in AppointmentError."""
    db = AsyncMock()

    with (
        patch(_PATCH_DELETE_EVENT, new_callable=AsyncMock, side_effect=CalendarError("err")),
        pytest.raises(AppointmentError),
    ):
        await cancel_appointment(db, _CLIENT_ID, "evt1")


@pytest.mark.asyncio
async def test_find_slot_in_window_raises_on_calendar_error():
    """CalendarError from get_free_slots is wrapped in AppointmentError."""
    db = AsyncMock()

    with (
        patch(_PATCH_GET_FREE_SLOTS, new_callable=AsyncMock, side_effect=CalendarError("err")),
        pytest.raises(AppointmentError),
    ):
        await find_slot_in_window(db, _CLIENT_ID, _SLOT, _SLOT + timedelta(days=7))


@pytest.mark.asyncio
async def test_find_appointment_raises_on_calendar_error():
    """CalendarError from _get_calendar_service is wrapped in AppointmentError."""
    db = _make_db_with_client()

    with (
        patch(
            _PATCH_GET_CAL_SVC,
            new_callable=AsyncMock,
            side_effect=CalendarError("no token"),
        ),
        pytest.raises(AppointmentError),
    ):
        await find_appointment(db, _CLIENT_ID, "Alice", _SLOT)
