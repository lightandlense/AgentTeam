import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.client import Client
from app.services.appointment import (
    AppointmentError,
    BookingRequest,
    book_appointment,
    cancel_appointment,
    find_appointment,
    find_appointment_by_phone,
    find_slot_in_window,
    reschedule_appointment,
)
from app.services.calendar import CalendarError, get_free_slots
from app.services.email import (
    send_callback_request,
    send_caller_confirmation,
    send_owner_alert,
)
from app.services.rag import TRANSFER_SENTINEL, answer_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retell", tags=["retell"])


async def _get_client_meta(db: AsyncSession, client_id: str) -> tuple[str, str, str]:
    """Return (owner_email, business_name, timezone) for a client_id."""
    try:
        result = await db.execute(select(Client).where(Client.client_id == client_id))
        client = result.scalar_one_or_none()
        if client is None:
            return ("", "", "UTC")
        return (client.owner_email, client.business_name, client.timezone)
    except Exception as exc:
        logger.warning("Could not load client meta for %s: %s", client_id, exc)
        return ("", "", "UTC")


async def _safe_send(coro) -> None:
    """Await an email coroutine, swallowing any exception."""
    try:
        await coro
    except Exception as exc:
        logger.error("Email send failed (suppressed): %s", exc)


def _args_from_body(body: dict) -> dict:
    """Extract tool arguments from either Simple Prompt or Conversation Flow format.

    Simple Prompt: body = {event, name, tool_call_id, arguments: {...}}
    Conversation Flow: body = {tool_call_id, param1, param2, ...}
    """
    if "arguments" in body:
        return body.get("arguments", {})
    # Conversation Flow — params are at top level; exclude meta keys
    return {k: v for k, v in body.items() if k not in ("tool_call_id",)}


# ---------------------------------------------------------------------------
# Shared dispatcher (Simple Prompt agents)
# ---------------------------------------------------------------------------

@router.post("/webhook")
async def retell_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Entry point for Simple Prompt tool calls (event-based dispatch)."""
    body = await request.json()

    event = body.get("event")

    # Non-tool events from Simple Prompt agents
    if event and event != "tool_call":
        return {"status": "received"}

    tool_name = body.get("name")
    tool_call_id = body.get("tool_call_id", "")
    args = _args_from_body(body)

    return await _dispatch(tool_name, tool_call_id, args, db)


# ---------------------------------------------------------------------------
# Per-tool endpoints (Conversation Flow nodes)
# ---------------------------------------------------------------------------

@router.post("/check_availability")
async def retell_check_availability(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    tool_call_id = body.get("tool_call_id", "")
    args = _args_from_body(body)
    return await _dispatch("check_availability", tool_call_id, args, db)


@router.post("/book_appointment")
async def retell_book_appointment(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    tool_call_id = body.get("tool_call_id", "")
    args = _args_from_body(body)
    return await _dispatch("book_appointment", tool_call_id, args, db)


@router.post("/find_appointment")
async def retell_find_appointment(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    tool_call_id = body.get("tool_call_id", "")
    args = _args_from_body(body)
    return await _dispatch("find_appointment", tool_call_id, args, db)


@router.post("/reschedule_appointment")
async def retell_reschedule_appointment(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    tool_call_id = body.get("tool_call_id", "")
    args = _args_from_body(body)
    return await _dispatch("reschedule_appointment", tool_call_id, args, db)


@router.post("/cancel_appointment")
async def retell_cancel_appointment(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    tool_call_id = body.get("tool_call_id", "")
    args = _args_from_body(body)
    return await _dispatch("cancel_appointment", tool_call_id, args, db)


@router.post("/answer_question")
async def retell_answer_question(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    tool_call_id = body.get("tool_call_id", "")
    args = _args_from_body(body)
    return await _dispatch("answer_question", tool_call_id, args, db)


@router.post("/request_callback")
async def retell_request_callback(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    tool_call_id = body.get("tool_call_id", "")
    args = _args_from_body(body)
    return await _dispatch("request_callback", tool_call_id, args, db)


# ---------------------------------------------------------------------------
# Core dispatcher
# ---------------------------------------------------------------------------

async def _dispatch(tool_name: str, tool_call_id: str, args: dict, db: AsyncSession) -> dict:
    """Route a tool call to the appropriate handler."""

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
                owner_email, business_name, _ = await _get_client_meta(db, client_id)
                caller_name = args.get("caller_name", "Unknown")
                caller_phone = args.get("caller_phone", "Unknown")
                await _safe_send(send_callback_request(
                    owner_email=owner_email,
                    business_name=business_name,
                    caller_name=caller_name,
                    caller_phone=caller_phone,
                    reason="no_slot_found",
                ))
            else:
                result = {"slots": [s.isoformat() for s in slots]}
        except (AppointmentError, CalendarError) as exc:
            logger.exception("CalendarError/AppointmentError in check_availability: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        except Exception as exc:
            logger.exception("Unexpected error in check_availability: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "book_appointment":
        try:
            client_id = args.get("client_id", "")
            slot_str = args.get("slot") or args.get("requested_slot")
            requested_slot = datetime.fromisoformat(slot_str)
            booking_req = BookingRequest(
                name=args.get("caller_name") or args.get("name", ""),
                phone=args.get("caller_phone") or args.get("phone", ""),
                email=args.get("caller_email") or args.get("email", ""),
                address=args.get("caller_address") or args.get("address", ""),
                problem_description=args.get("summary") or args.get("problem_description", ""),
                access_notes=args.get("property_notes") or args.get("access_notes", ""),
            )
            booking = await book_appointment(db, client_id, requested_slot, booking_req)
            if booking.confirmed:
                result = {
                    "confirmed": True,
                    "event_id": booking.event_id,
                    "slot": booking.slot.isoformat(),
                }
                owner_email, business_name, tz = await _get_client_meta(db, client_id)
                await _safe_send(send_caller_confirmation(
                    caller_email=booking_req.email,
                    caller_name=booking_req.name,
                    business_name=business_name,
                    action="booked",
                    appointment_dt=booking.slot,
                    business_timezone=tz,
                ))
                await _safe_send(send_owner_alert(
                    owner_email=owner_email,
                    business_name=business_name,
                    action="booked",
                    caller_name=booking_req.name,
                    caller_phone=booking_req.phone,
                    caller_email=booking_req.email,
                    appointment_dt=booking.slot,
                    business_timezone=tz,
                ))
            else:
                result = {
                    "confirmed": False,
                    "alternatives": [s.isoformat() for s in booking.alternatives],
                }
        except AppointmentError as exc:
            logger.exception("AppointmentError in book_appointment: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        except Exception as exc:
            logger.exception("Unexpected error in book_appointment: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "find_slot_in_window":
        try:
            client_id = args.get("client_id", "")
            window_start = datetime.fromisoformat(args.get("window_start"))
            window_end = datetime.fromisoformat(args.get("window_end"))
            slots = await find_slot_in_window(db, client_id, window_start, window_end)
            result = {"slots": [s.isoformat() for s in slots]} if slots else TRANSFER_SENTINEL
            if not slots:
                owner_email, business_name, _ = await _get_client_meta(db, client_id)
                caller_name = args.get("caller_name", "Unknown")
                caller_phone = args.get("caller_phone", "Unknown")
                await _safe_send(send_callback_request(
                    owner_email=owner_email,
                    business_name=business_name,
                    caller_name=caller_name,
                    caller_phone=caller_phone,
                    reason="no_slot_found",
                ))
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
            owner_email, business_name, tz = await _get_client_meta(db, client_id)
            caller_name = args.get("caller_name") or args.get("name", "")
            caller_phone = args.get("caller_phone") or args.get("phone", "")
            caller_email_addr = args.get("caller_email") or args.get("email", "")
            await _safe_send(send_caller_confirmation(
                caller_email=caller_email_addr,
                caller_name=caller_name,
                business_name=business_name,
                action="rescheduled",
                appointment_dt=new_start_dt,
                business_timezone=tz,
            ))
            await _safe_send(send_owner_alert(
                owner_email=owner_email,
                business_name=business_name,
                action="rescheduled",
                caller_name=caller_name,
                caller_phone=caller_phone,
                caller_email=caller_email_addr,
                appointment_dt=new_start_dt,
                business_timezone=tz,
            ))
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
            owner_email, business_name, tz = await _get_client_meta(db, client_id)
            caller_name = args.get("caller_name") or args.get("name", "")
            caller_phone = args.get("caller_phone") or args.get("phone", "")
            caller_email_addr = args.get("caller_email") or args.get("email", "")
            await _safe_send(send_caller_confirmation(
                caller_email=caller_email_addr,
                caller_name=caller_name,
                business_name=business_name,
                action="cancelled",
                appointment_dt=None,
                business_timezone=tz,
            ))
            await _safe_send(send_owner_alert(
                owner_email=owner_email,
                business_name=business_name,
                action="cancelled",
                caller_name=caller_name,
                caller_phone=caller_phone,
                caller_email=caller_email_addr,
                appointment_dt=None,
                business_timezone=tz,
            ))
        except AppointmentError as exc:
            logger.exception("AppointmentError in cancel_appointment: %s", exc)
            return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "find_appointment":
        try:
            client_id = args.get("client_id", "")
            caller_phone = args.get("caller_phone", "")
            caller_name = args.get("caller_name", "")
            appointment_date = args.get("appointment_date", "")

            if caller_phone:
                matches = await find_appointment_by_phone(db, client_id, caller_phone)
            else:
                matches = await find_appointment(
                    db, client_id, caller_name,
                    datetime.fromisoformat(appointment_date) if appointment_date else datetime.now(),
                )

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

    elif tool_name == "request_callback":
        client_id = args.get("client_id", "")
        caller_name = args.get("caller_name", "Unknown")
        caller_phone = args.get("caller_phone", "Unknown")
        owner_email, business_name, _ = await _get_client_meta(db, client_id)
        await _safe_send(send_callback_request(
            owner_email=owner_email,
            business_name=business_name,
            caller_name=caller_name,
            caller_phone=caller_phone,
            reason="caller_requested",
        ))
        return {"tool_call_id": tool_call_id, "result": TRANSFER_SENTINEL}

    return {"tool_call_id": tool_call_id, "result": "not_implemented"}
