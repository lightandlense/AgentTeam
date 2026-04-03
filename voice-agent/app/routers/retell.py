from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.rag import answer_question

router = APIRouter(prefix="/retell", tags=["retell"])


@router.post("/webhook")
async def retell_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Entry point for all Retell tool calls.

    Handles the ``answer_question`` tool call by dispatching to the RAG
    service.  All other events are acknowledged with a generic received status
    or a not_implemented result for unknown tools.
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

    # Unknown tool — acknowledge without crashing
    return {"tool_call_id": tool_call_id, "result": "not_implemented"}


@router.post("/tools/check_calendar_availability")
async def check_calendar_availability(db: AsyncSession = Depends(get_db)):
    return {"error": "not_implemented"}, 501


@router.post("/tools/book_appointment")
async def book_appointment(db: AsyncSession = Depends(get_db)):
    return {"error": "not_implemented"}, 501


@router.post("/tools/transfer_call")
async def transfer_call(db: AsyncSession = Depends(get_db)):
    return {"error": "not_implemented"}, 501


@router.post("/tools/end_call")
async def end_call(db: AsyncSession = Depends(get_db)):
    return {"error": "not_implemented"}, 501
