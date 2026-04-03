from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/retell", tags=["retell"])


@router.post("/webhook")
async def retell_webhook(db: AsyncSession = Depends(get_db)):
    """Entry point for all Retell tool calls. Phase 2+ implements dispatch logic."""
    return {"status": "received"}


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
