"""Tests verifying email notification calls from the Retell webhook handler.

Each test patches the email functions at the call site (app.routers.retell) and
_get_client_meta to avoid DB setup. Webhook calls are signed with HMAC matching
the pattern in test_retell_calendar.py.
"""

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("RETELL_WEBHOOK_SECRET", "test-secret")

from app.main import app  # noqa: E402
from app.services.appointment import AppointmentError, BookingResult  # noqa: E402
from app.services.rag import TRANSFER_SENTINEL  # noqa: E402

SECRET = os.environ["RETELL_WEBHOOK_SECRET"]
WEBHOOK_URL = "/retell/webhook"
SLOT1 = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

_FAKE_META = ("owner@test.com", "Test Biz", "UTC")


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


async def _post(client: AsyncClient, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    response = await client.post(
        WEBHOOK_URL,
        content=body,
        headers={
            "X-Retell-Signature": _sign(body),
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _tool_call(name: str, tool_call_id: str, arguments: dict) -> dict:
    return {
        "event": "tool_call",
        "name": name,
        "tool_call_id": tool_call_id,
        "arguments": arguments,
    }


# ---------------------------------------------------------------------------
# book_appointment — confirmed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_book_confirmed_sends_caller_and_owner_emails():
    confirmed_result = BookingResult(confirmed=True, event_id="ev1", slot=SLOT1, alternatives=[])
    payload = _tool_call(
        "book_appointment",
        "notif-1",
        {
            "client_id": "galvan",
            "requested_slot": SLOT1.isoformat(),
            "name": "Jane Doe",
            "phone": "555-1234",
            "email": "jane@example.com",
            "address": "123 Main St",
            "problem_description": "Boiler broken",
            "access_notes": "",
        },
    )
    mock_caller = AsyncMock()
    mock_owner = AsyncMock()
    with (
        patch("app.routers.retell.book_appointment", new=AsyncMock(return_value=confirmed_result)),
        patch("app.routers.retell._get_client_meta", new=AsyncMock(return_value=_FAKE_META)),
        patch("app.routers.retell.send_caller_confirmation", new=mock_caller),
        patch("app.routers.retell.send_owner_alert", new=mock_owner),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["result"]["confirmed"] is True
    mock_caller.assert_called_once()
    call_kwargs = mock_caller.call_args.kwargs
    assert call_kwargs["action"] == "booked"
    assert call_kwargs["caller_email"] == "jane@example.com"

    mock_owner.assert_called_once()
    owner_kwargs = mock_owner.call_args.kwargs
    assert owner_kwargs["action"] == "booked"


# ---------------------------------------------------------------------------
# book_appointment — unconfirmed (alternatives only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_book_unconfirmed_sends_no_emails():
    alt_result = BookingResult(
        confirmed=False, event_id=None, slot=None, alternatives=[SLOT1]
    )
    payload = _tool_call(
        "book_appointment",
        "notif-2",
        {
            "client_id": "galvan",
            "requested_slot": SLOT1.isoformat(),
            "name": "Jane Doe",
            "phone": "555-1234",
            "email": "jane@example.com",
            "address": "123 Main St",
            "problem_description": "Boiler broken",
            "access_notes": "",
        },
    )
    mock_caller = AsyncMock()
    mock_owner = AsyncMock()
    with (
        patch("app.routers.retell.book_appointment", new=AsyncMock(return_value=alt_result)),
        patch("app.routers.retell._get_client_meta", new=AsyncMock(return_value=_FAKE_META)),
        patch("app.routers.retell.send_caller_confirmation", new=mock_caller),
        patch("app.routers.retell.send_owner_alert", new=mock_owner),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["result"]["confirmed"] is False
    mock_caller.assert_not_called()
    mock_owner.assert_not_called()


# ---------------------------------------------------------------------------
# reschedule_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reschedule_sends_caller_and_owner_emails():
    payload = _tool_call(
        "reschedule_appointment",
        "notif-3",
        {
            "client_id": "galvan",
            "event_id": "evt1",
            "new_start": SLOT1.isoformat(),
            "slot_duration_minutes": 60,
            "name": "Jane Doe",
            "phone": "555-1234",
            "email": "jane@example.com",
        },
    )
    mock_caller = AsyncMock()
    mock_owner = AsyncMock()
    with (
        patch("app.routers.retell.reschedule_appointment", new=AsyncMock(return_value="evt2")),
        patch("app.routers.retell._get_client_meta", new=AsyncMock(return_value=_FAKE_META)),
        patch("app.routers.retell.send_caller_confirmation", new=mock_caller),
        patch("app.routers.retell.send_owner_alert", new=mock_owner),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["result"] == {"confirmed": True, "event_id": "evt2"}
    mock_caller.assert_called_once()
    assert mock_caller.call_args.kwargs["action"] == "rescheduled"
    mock_owner.assert_called_once()
    assert mock_owner.call_args.kwargs["action"] == "rescheduled"


# ---------------------------------------------------------------------------
# cancel_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_sends_caller_and_owner_emails():
    payload = _tool_call(
        "cancel_appointment",
        "notif-4",
        {
            "client_id": "galvan",
            "event_id": "evt1",
            "name": "Jane Doe",
            "phone": "555-1234",
            "email": "jane@example.com",
        },
    )
    mock_caller = AsyncMock()
    mock_owner = AsyncMock()
    with (
        patch("app.routers.retell.cancel_appointment", new=AsyncMock(return_value=None)),
        patch("app.routers.retell._get_client_meta", new=AsyncMock(return_value=_FAKE_META)),
        patch("app.routers.retell.send_caller_confirmation", new=mock_caller),
        patch("app.routers.retell.send_owner_alert", new=mock_owner),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["result"] == {"confirmed": True}
    mock_caller.assert_called_once()
    assert mock_caller.call_args.kwargs["action"] == "cancelled"
    mock_owner.assert_called_once()
    assert mock_owner.call_args.kwargs["action"] == "cancelled"


# ---------------------------------------------------------------------------
# check_availability — no slots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_availability_no_slots_sends_callback():
    payload = _tool_call(
        "check_availability",
        "notif-5",
        {
            "client_id": "galvan",
            "window_start": "2026-06-15T08:00:00+00:00",
            "window_end": "2026-06-15T18:00:00+00:00",
            "caller_name": "Bob Smith",
            "caller_phone": "555-9999",
        },
    )
    mock_callback = AsyncMock()
    with (
        patch("app.routers.retell.get_free_slots", new=AsyncMock(return_value=[])),
        patch("app.routers.retell._get_client_meta", new=AsyncMock(return_value=_FAKE_META)),
        patch("app.routers.retell.send_callback_request", new=mock_callback),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["result"] == TRANSFER_SENTINEL
    mock_callback.assert_called_once()
    assert mock_callback.call_args.kwargs["reason"] == "no_slot_found"


# ---------------------------------------------------------------------------
# check_availability — has slots (no callback)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_availability_has_slots_no_callback():
    payload = _tool_call(
        "check_availability",
        "notif-6",
        {
            "client_id": "galvan",
            "window_start": "2026-06-15T08:00:00+00:00",
            "window_end": "2026-06-15T18:00:00+00:00",
        },
    )
    mock_callback = AsyncMock()
    with (
        patch("app.routers.retell.get_free_slots", new=AsyncMock(return_value=[SLOT1])),
        patch("app.routers.retell._get_client_meta", new=AsyncMock(return_value=_FAKE_META)),
        patch("app.routers.retell.send_callback_request", new=mock_callback),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["result"]["slots"] == [SLOT1.isoformat()]
    mock_callback.assert_not_called()


# ---------------------------------------------------------------------------
# find_slot_in_window — no slots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_slot_in_window_no_slots_sends_callback():
    payload = _tool_call(
        "find_slot_in_window",
        "notif-7",
        {
            "client_id": "galvan",
            "window_start": "2026-06-15T08:00:00+00:00",
            "window_end": "2026-06-20T18:00:00+00:00",
            "caller_name": "Alice",
            "caller_phone": "555-1111",
        },
    )
    mock_callback = AsyncMock()
    with (
        patch("app.routers.retell.find_slot_in_window", new=AsyncMock(return_value=[])),
        patch("app.routers.retell._get_client_meta", new=AsyncMock(return_value=_FAKE_META)),
        patch("app.routers.retell.send_callback_request", new=mock_callback),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["result"] == TRANSFER_SENTINEL
    mock_callback.assert_called_once()
    assert mock_callback.call_args.kwargs["reason"] == "no_slot_found"


# ---------------------------------------------------------------------------
# request_callback tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_callback_tool_sends_callback_and_transfers():
    payload = _tool_call(
        "request_callback",
        "notif-8",
        {
            "client_id": "galvan",
            "caller_name": "John Caller",
            "caller_phone": "555-2222",
        },
    )
    mock_callback = AsyncMock()
    with (
        patch("app.routers.retell._get_client_meta", new=AsyncMock(return_value=_FAKE_META)),
        patch("app.routers.retell.send_callback_request", new=mock_callback),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["result"] == TRANSFER_SENTINEL
    mock_callback.assert_called_once()
    assert mock_callback.call_args.kwargs["reason"] == "caller_requested"
    assert mock_callback.call_args.kwargs["caller_name"] == "John Caller"
    assert mock_callback.call_args.kwargs["caller_phone"] == "555-2222"


# ---------------------------------------------------------------------------
# Email failure does not break booking response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_failure_does_not_break_booking_response():
    confirmed_result = BookingResult(confirmed=True, event_id="ev1", slot=SLOT1, alternatives=[])
    payload = _tool_call(
        "book_appointment",
        "notif-9",
        {
            "client_id": "galvan",
            "requested_slot": SLOT1.isoformat(),
            "name": "Jane Doe",
            "phone": "555-1234",
            "email": "jane@example.com",
            "address": "123 Main St",
            "problem_description": "Boiler broken",
            "access_notes": "",
        },
    )
    # send_caller_confirmation raises to simulate SMTP failure
    mock_caller = AsyncMock(side_effect=Exception("SMTP connection refused"))
    mock_owner = AsyncMock()
    with (
        patch("app.routers.retell.book_appointment", new=AsyncMock(return_value=confirmed_result)),
        patch("app.routers.retell._get_client_meta", new=AsyncMock(return_value=_FAKE_META)),
        patch("app.routers.retell.send_caller_confirmation", new=mock_caller),
        patch("app.routers.retell.send_owner_alert", new=mock_owner),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    # The webhook must still return confirmed=True despite the email failure
    assert data["result"]["confirmed"] is True
    assert data["result"]["event_id"] == "ev1"
