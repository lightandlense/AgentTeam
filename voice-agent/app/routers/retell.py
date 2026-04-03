import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.appointment import (
    AppointmentError,
    BookingRequest,
    book_appointment,
    cancel_appointment,
    find_appointment,
    find_slot_in_window,
    reschedule_appointment,
)
from app.services.calendar import CalendarError, get_free_slots
from app.services.rag import TRANSFER_SENTINEL, answer_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retell", tags=["retell"])


@router.post("/webhook")
async def retell_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Entry point for all Retell tool calls.

    Handles tool_call events by dispatching to the appropriate service.
    Non-tool events are acknowledged with a generic received status.
    AppointmentError from any calendar tool returns TRANSFER_SENTINEL.
    """
    body = await request.json()

    # Only handle tool_call events; ignore others (e.g. call_started, call_ended)
    if body.get("event") != "tool_call":
        return {"status": "received"}

    tool_name = body.get("name")
    tool_call_id = body.get("tool_call_id", "")
    args = body.get("arguments", {})

    if tool_name == "answer_question":
        client_id = args.get("client_id", "")
        question = args.get("question", "")
        result = await answer_question(db, client_id, question)
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "check_availability":
        try:
            client_id = args.get("client_id", "")
            window_start = datetime.fromisoformat(args.get("window_start"))
            window_end = datetime.fromisoformat(args.get("window_end"))
            slots = await get_free_slots(db, client_id, window_start, window_end, max_slots=3)
            if not slots:
                result = TRANSFER_SENTINEL
            else:
                result = {"slots": [s.isoformat() for s in slots]}
        except (AppointmentError, CalendarError) as exc:
            logger.exception("CalendarError/AppointmentError in check_availability: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "book_appointment":
        try:
            client_id = args.get("client_id", "")
            requested_slot = datetime.fromisoformat(args.get("requested_slot"))
            booking_req = BookingRequest(
                name=args.get("name", ""),
                phone=args.get("phone", ""),
                email=args.get("email", ""),
                address=args.get("address", ""),
                problem_description=args.get("problem_description", ""),
                access_notes=args.get("access_notes", ""),
            )
            booking = await book_appointment(db, client_id, requested_slot, booking_req)
            if booking.confirmed:
                result = {
                    "confirmed": True,
                    "event_id": booking.event_id,
                    "slot": booking.slot.isoformat(),
                }
            else:
                result = {
                    "confirmed": False,
                    "alternatives": [s.isoformat() for s in booking.alternatives],
                }
        except AppointmentError as exc:
            logger.exception("AppointmentError in book_appointment: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "find_slot_in_window":
        try:
            client_id = args.get("client_id", "")
            window_start = datetime.fromisoformat(args.get("window_start"))
            window_end = datetime.fromisoformat(args.get("window_end"))
            slots = await find_slot_in_window(db, client_id, window_start, window_end)
            result = {"slots": [s.isoformat() for s in slots]} if slots else TRANSFER_SENTINEL
        except AppointmentError as exc:
            logger.exception("AppointmentError in find_slot_in_window: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "reschedule_appointment":
        try:
            client_id = args.get("client_id", "")
            event_id = args.get("event_id", "")
            new_start_dt = datetime.fromisoformat(args.get("new_start"))
            slot_duration = int(args.get("slot_duration_minutes", 60))
            event_id_out = await reschedule_appointment(
                db, client_id, event_id, new_start_dt, slot_duration
            )
            result = {"confirmed": True, "event_id": event_id_out}
        except AppointmentError as exc:
            logger.exception("AppointmentError in reschedule_appointment: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "cancel_appointment":
        try:
            client_id = args.get("client_id", "")
            event_id = args.get("event_id", "")
            await cancel_appointment(db, client_id, event_id)
            result = {"confirmed": True}
        except AppointmentError as exc:
            logger.exception("AppointmentError in cancel_appointment: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "find_appointment":
        try:
            client_id = args.get("client_id", "")
            caller_name = args.get("caller_name", "")
            appointment_date = datetime.fromisoformat(args.get("appointment_date"))
            matches = await find_appointment(db, client_id, caller_name, appointment_date)
            if not matches:
                result = {"found": False}
            else:
                result = {
                    "found": True,
                    "appointments": [
                        {
                            "event_id": m.event_id,
                            "summary": m.summary,
                            "start": m.start.isoformat(),
                            "end": m.end.isoformat(),
                        }
                        for m in matches
                    ],
                }
        except AppointmentError as exc:
            logger.exception("AppointmentError in find_appointment: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        return {"tool_call_id": tool_call_id, "result": result}

    # Unknown tool — acknowledge without crashing
    return {"tool_call_id": tool_call_id, "result": "not_implemented"}
