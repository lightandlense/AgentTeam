"""Integration-style tests for calendar tool dispatch through the Retell webhook.

All tests post signed tool_call events to /retell/webhook and assert the
correct result payloads. Appointment and calendar service functions are
patched at the call site (app.routers.retell) to avoid real network calls.
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
from app.services.appointment import AppointmentError, AppointmentMatch, BookingResult  # noqa: E402
from app.services.rag import TRANSFER_SENTINEL  # noqa: E402

SECRET = os.environ["RETELL_WEBHOOK_SECRET"]
WEBHOOK_URL = "/retell/webhook"

SLOT1 = datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
SLOT2 = datetime(2026, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
ALT1 = datetime(2026, 6, 16, 10, 0, 0, tzinfo=timezone.utc)
ALT2 = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)


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
# check_availability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_availability_returns_slots():
    payload = _tool_call(
        "check_availability",
        "tc-1",
        {
            "client_id": "galvan",
            "window_start": "2026-06-15T08:00:00+00:00",
            "window_end": "2026-06-15T18:00:00+00:00",
        },
    )
    with patch(
        "app.routers.retell.get_free_slots", new=AsyncMock(return_value=[SLOT1, SLOT2])
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-1"
    assert data["result"]["slots"] == [SLOT1.isoformat(), SLOT2.isoformat()]


@pytest.mark.asyncio
async def test_check_availability_transfers_when_no_slots():
    payload = _tool_call(
        "check_availability",
        "tc-2",
        {
            "client_id": "galvan",
            "window_start": "2026-06-15T08:00:00+00:00",
            "window_end": "2026-06-15T18:00:00+00:00",
        },
    )
    with patch(
        "app.routers.retell.get_free_slots", new=AsyncMock(return_value=[])
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-2"
    assert data["result"] == TRANSFER_SENTINEL


# ---------------------------------------------------------------------------
# book_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_book_appointment_confirmed():
    confirmed_result = BookingResult(
        confirmed=True, event_id="evt1", slot=SLOT1, alternatives=[]
    )
    payload = _tool_call(
        "book_appointment",
        "tc-3",
        {
            "client_id": "galvan",
            "requested_slot": SLOT1.isoformat(),
            "name": "Jane Doe",
            "phone": "555-1234",
            "email": "jane@example.com",
            "address": "123 Main St",
            "problem_description": "Boiler broken",
            "access_notes": "Gate code 1234",
        },
    )
    with patch(
        "app.routers.retell.book_appointment", new=AsyncMock(return_value=confirmed_result)
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-3"
    assert data["result"]["confirmed"] is True
    assert data["result"]["event_id"] == "evt1"
    assert data["result"]["slot"] == SLOT1.isoformat()


@pytest.mark.asyncio
async def test_book_appointment_offers_alternatives():
    alt_result = BookingResult(
        confirmed=False, event_id=None, slot=None, alternatives=[ALT1, ALT2]
    )
    payload = _tool_call(
        "book_appointment",
        "tc-4",
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
    with patch(
        "app.routers.retell.book_appointment", new=AsyncMock(return_value=alt_result)
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-4"
    assert data["result"]["confirmed"] is False
    assert data["result"]["alternatives"] == [ALT1.isoformat(), ALT2.isoformat()]


# ---------------------------------------------------------------------------
# find_slot_in_window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_slot_in_window_returns_slots():
    payload = _tool_call(
        "find_slot_in_window",
        "tc-5",
        {
            "client_id": "galvan",
            "window_start": "2026-06-15T08:00:00+00:00",
            "window_end": "2026-06-20T18:00:00+00:00",
        },
    )
    with patch(
        "app.routers.retell.find_slot_in_window", new=AsyncMock(return_value=[SLOT1])
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-5"
    assert data["result"]["slots"] == [SLOT1.isoformat()]


@pytest.mark.asyncio
async def test_find_slot_in_window_transfers_when_empty():
    payload = _tool_call(
        "find_slot_in_window",
        "tc-6",
        {
            "client_id": "galvan",
            "window_start": "2026-06-15T08:00:00+00:00",
            "window_end": "2026-06-20T18:00:00+00:00",
        },
    )
    with patch(
        "app.routers.retell.find_slot_in_window", new=AsyncMock(return_value=[])
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-6"
    assert data["result"] == TRANSFER_SENTINEL


# ---------------------------------------------------------------------------
# reschedule_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reschedule_appointment_confirmed():
    payload = _tool_call(
        "reschedule_appointment",
        "tc-7",
        {
            "client_id": "galvan",
            "event_id": "evt1",
            "new_start": SLOT2.isoformat(),
            "slot_duration_minutes": 60,
        },
    )
    with patch(
        "app.routers.retell.reschedule_appointment", new=AsyncMock(return_value="evt1")
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-7"
    assert data["result"] == {"confirmed": True, "event_id": "evt1"}


# ---------------------------------------------------------------------------
# cancel_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_appointment_confirmed():
    payload = _tool_call(
        "cancel_appointment",
        "tc-8",
        {"client_id": "galvan", "event_id": "evt1"},
    )
    with patch(
        "app.routers.retell.cancel_appointment", new=AsyncMock(return_value=None)
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-8"
    assert data["result"] == {"confirmed": True}


# ---------------------------------------------------------------------------
# find_appointment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_appointment_found():
    match = AppointmentMatch(
        event_id="e1",
        summary="John Smith",
        start=SLOT1,
        end=SLOT2,
    )
    payload = _tool_call(
        "find_appointment",
        "tc-9",
        {
            "client_id": "galvan",
            "caller_name": "John Smith",
            "appointment_date": "2026-06-15T00:00:00",
        },
    )
    with patch(
        "app.routers.retell.find_appointment", new=AsyncMock(return_value=[match])
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-9"
    assert data["result"]["found"] is True
    appts = data["result"]["appointments"]
    assert len(appts) == 1
    assert appts[0]["event_id"] == "e1"
    assert appts[0]["summary"] == "John Smith"
    assert appts[0]["start"] == SLOT1.isoformat()
    assert appts[0]["end"] == SLOT2.isoformat()


@pytest.mark.asyncio
async def test_find_appointment_not_found():
    payload = _tool_call(
        "find_appointment",
        "tc-10",
        {
            "client_id": "galvan",
            "caller_name": "Unknown Person",
            "appointment_date": "2026-06-15T00:00:00",
        },
    )
    with patch(
        "app.routers.retell.find_appointment", new=AsyncMock(return_value=[])
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-10"
    assert data["result"] == {"found": False}


# ---------------------------------------------------------------------------
# AppointmentError fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_appointment_error_returns_transfer():
    payload = _tool_call(
        "book_appointment",
        "tc-11",
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
    with patch(
        "app.routers.retell.book_appointment",
        new=AsyncMock(side_effect=AppointmentError("something failed")),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-11"
    assert data["result"] == TRANSFER_SENTINEL


# ---------------------------------------------------------------------------
# Existing answer_question dispatch still works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_existing_answer_question_unchanged():
    payload = _tool_call(
        "answer_question",
        "tc-12",
        {"client_id": "galvan", "question": "What are your hours?"},
    )
    with patch(
        "app.routers.retell.answer_question", new=AsyncMock(return_value="We're open 9-5")
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            data = await _post(client, payload)

    assert data["tool_call_id"] == "tc-12"
    assert data["result"] == "We're open 9-5"
