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


_META_KEYS = {"tool_call_id", "id", "event", "name", "call_id"}


def _extract_tool_call_id(body: dict) -> str:
    """Extract tool call ID — Retell uses different field names across modes."""
    return body.get("tool_call_id") or body.get("id") or body.get("call_id") or ""


def _args_from_body(body: dict) -> dict:
    """Extract tool arguments from Retell webhook body.

    Handles multiple formats:
    - Simple Prompt: {event, name, tool_call_id, arguments: {...}}
    - Conversation Flow v1: {tool_call_id, args: {...}}
    - Conversation Flow v2: {tool_call_id, input: {...}}
    - Conversation Flow flat: {tool_call_id, param1, param2, ...}
    """
    print("RETELL_BODY_KEYS:", list(body.keys()), flush=True)
    print("RETELL_BODY:", body, flush=True)
    if "arguments" in body:
        return body["arguments"]
    if "args" in body:
        return body["args"]
    if "input" in body:
        return body["input"]
    # Flat format — params at top level; exclude meta keys
    return {k: v for k, v in body.items() if k not in _META_KEYS}


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
    tool_call_id = _extract_tool_call_id(body)
    args = _args_from_body(body)

    return await _dispatch(tool_name, tool_call_id, args, db)


# ---------------------------------------------------------------------------
# Per-tool endpoints (Conversation Flow nodes)
# Retell sends GET to validate endpoint, then POST for actual tool calls.
# ---------------------------------------------------------------------------

def _tool_route(tool_name: str):
    """Factory: returns (GET validator, POST handler) for a Conversation Flow tool endpoint."""
    async def get_handler():
        return {"status": "ok", "tool": tool_name}

    async def post_handler(request: Request, db: AsyncSession = Depends(get_db)):
        body = await request.json()
        tool_call_id = _extract_tool_call_id(body)
        args = _args_from_body(body)
        return await _dispatch(tool_name, tool_call_id, args, db)

    return get_handler, post_handler


_ca_get, _ca_post = _tool_route("check_availability")
router.add_api_route("/check_availability", _ca_get, methods=["GET"])
router.add_api_route("/check_availability", _ca_post, methods=["POST"])

_ba_get, _ba_post = _tool_route("book_appointment")
router.add_api_route("/book_appointment", _ba_get, methods=["GET"])
router.add_api_route("/book_appointment", _ba_post, methods=["POST"])

_fa_get, _fa_post = _tool_route("find_appointment")
router.add_api_route("/find_appointment", _fa_get, methods=["GET"])
router.add_api_route("/find_appointment", _fa_post, methods=["POST"])

_ra_get, _ra_post = _tool_route("reschedule_appointment")
router.add_api_route("/reschedule_appointment", _ra_get, methods=["GET"])
router.add_api_route("/reschedule_appointment", _ra_post, methods=["POST"])

_cna_get, _cna_post = _tool_route("cancel_appointment")
router.add_api_route("/cancel_appointment", _cna_get, methods=["GET"])
router.add_api_route("/cancel_appointment", _cna_post, methods=["POST"])

_aq_get, _aq_post = _tool_route("answer_question")
router.add_api_route("/answer_question", _aq_get, methods=["GET"])
router.add_api_route("/answer_question", _aq_post, methods=["POST"])

_rc_get, _rc_post = _tool_route("request_callback")
router.add_api_route("/request_callback", _rc_get, methods=["GET"])
router.add_api_route("/request_callback", _rc_post, methods=["POST"])

_gd_get, _gd_post = _tool_route("get_current_date")
router.add_api_route("/get_current_date", _gd_get, methods=["GET"])
router.add_api_route("/get_current_date", _gd_post, methods=["POST"])


# ---------------------------------------------------------------------------
# Core dispatcher
# ---------------------------------------------------------------------------

async def _dispatch(tool_name: str, tool_call_id: str, args: dict, db: AsyncSession) -> dict:
    """Route a tool call to the appropriate handler."""

    if tool_name == "get_current_date":
        now = datetime.now()
        return {
            "tool_call_id": tool_call_id,
            "result": {
                "date": now.strftime("%Y-%m-%d"),
                "day_of_week": now.strftime("%A"),
                "datetime": now.isoformat(),
            },
        }

    elif tool_name == "answer_question":
        client_id = args.get("client_id", "")
        question = args.get("question", "")
        result = await answer_question(db, client_id, question)
        return {"tool_call_id": tool_call_id, "result": result}

    elif tool_name == "check_availability":
        try:
            client_id = args.get("client_id", "")
            from datetime import timedelta
            now = datetime.now()
            window_start = datetime.fromisoformat(args.get("window_start"))
            window_end = datetime.fromisoformat(args.get("window_end"))
            # If the agent generated a past date, find the next future date
            # with the same day-of-week so "Wednesday" → next real Wednesday
            if window_start < now:
                duration = window_end - window_start
                days_ahead = (window_start.weekday() - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7  # same day of week → next week
                window_start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
                window_end = window_start + (duration if duration.total_seconds() > 0 else timedelta(days=1))
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
                await _safe_send(send_owner_alert(
                    owner_email=owner_email,
                    business_name=business_name,
                    action="booked",
                    caller_name=booking_req.name,
                    caller_phone=booking_req.phone,
                    caller_email=booking_req.email,
                    appointment_dt=booking.slot,
                    business_timezone=tz,
                    caller_address=booking_req.address,
                    problem_description=booking_req.problem_description,
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
