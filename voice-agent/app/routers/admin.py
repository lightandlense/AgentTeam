"""Admin router for knowledge-base document management.

Provides:
    GET  /admin/documents          — list documents for a client
    POST /admin/documents/upload   — upload and ingest a document
    POST /admin/documents/delete   — delete all chunks for a document
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.database import get_db
from app.models.client import Client, Embedding, OAuthToken
from app.services.ingestion import MAX_FILE_BYTES, delete_document, ingest_document

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router + templates
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/admin", tags=["admin"])

# Resolve template directory relative to this file's location so the router
# works regardless of the process working directory.
_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE.parent.parent / "admin" / "templates"

# Fall back to a cwd-relative path when running tests with a custom CWD.
templates = Jinja2Templates(
    directory=str(_TEMPLATES_DIR) if _TEMPLATES_DIR.exists() else "admin/templates"
)

_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".csv"})


# ---------------------------------------------------------------------------
# GET /admin/
# ---------------------------------------------------------------------------


@router.get("/")
async def client_list(request: Request, db: AsyncSession = Depends(get_db)):
    """Render a list of all clients."""
    result = await db.execute(select(Client).order_by(Client.business_name))
    clients = result.scalars().all()
    return templates.TemplateResponse(
        "client_list.html",
        {"request": request, "clients": clients},
    )


_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------------------
# GET /admin/client/{client_id}
# ---------------------------------------------------------------------------


@router.get("/client/{client_id}")
async def client_dashboard(
    client_id: str,
    request: Request,
    message: str = "",
    error: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Render the per-client management dashboard."""
    result = await db.execute(select(Client).where(Client.client_id == client_id))
    client = result.scalar_one_or_none()
    if client is None:
        return Response("Client not found", status_code=404)

    token_result = await db.execute(
        select(OAuthToken)
        .where(OAuthToken.client_id == client_id)
        .order_by(OAuthToken.id.desc())
        .limit(1)
    )
    token = token_result.scalar_one_or_none()

    doc_result = await db.execute(
        select(func.count(func.distinct(Embedding.doc_name))).where(
            Embedding.client_id == client_id
        )
    )
    doc_count = doc_result.scalar() or 0

    return templates.TemplateResponse(
        "client_dashboard.html",
        {
            "request": request,
            "client": client,
            "token": token,
            "doc_count": doc_count,
            "day_labels": _DAY_LABELS,
            "message": message,
            "error": error,
            "now": datetime.now(timezone.utc),
        },
    )


# ---------------------------------------------------------------------------
# GET /admin/documents
# ---------------------------------------------------------------------------


@router.get("/documents")
async def list_documents(
    request: Request,
    client_id: str,
    message: str = "",
    error: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Render the documents page for a given client."""
    stmt = (
        select(Embedding.doc_name, func.count().label("chunk_count"))
        .where(Embedding.client_id == client_id)
        .group_by(Embedding.doc_name)
    )
    result = await db.execute(stmt)
    documents = [
        {"doc_name": row.doc_name, "chunk_count": row.chunk_count}
        for row in result.all()
    ]

    logger.debug("list_documents: client=%s found %d docs", client_id, len(documents))

    return templates.TemplateResponse(
        "documents.html",
        {
            "request": request,
            "client_id": client_id,
            "documents": documents,
            "message": message,
            "error": error,
        },
    )


# ---------------------------------------------------------------------------
# POST /admin/documents/upload
# ---------------------------------------------------------------------------


@router.post("/documents/upload")
async def upload_document(
    request: Request,
    client_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document, ingest it, and redirect back to the document list."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        logger.warning("upload_document: unsupported extension '%s'", ext)
        # Re-render the page with an error message (no redirect — no DB query here).
        stmt = (
            select(Embedding.doc_name, func.count().label("chunk_count"))
            .where(Embedding.client_id == client_id)
            .group_by(Embedding.doc_name)
        )
        result = await db.execute(stmt)
        documents = [
            {"doc_name": row.doc_name, "chunk_count": row.chunk_count}
            for row in result.all()
        ]
        return templates.TemplateResponse(
            "documents.html",
            {
                "request": request,
                "client_id": client_id,
                "documents": documents,
                "message": f"Unsupported file type: '{ext}'. Allowed: .pdf, .docx, .txt, .csv",
                "error": True,
            },
        )

    content = await file.read()

    try:
        result_info = await ingest_document(db, client_id, file.filename or "", content)
    except ValueError as exc:
        logger.warning("upload_document: ingestion error: %s", exc)
        stmt = (
            select(Embedding.doc_name, func.count().label("chunk_count"))
            .where(Embedding.client_id == client_id)
            .group_by(Embedding.doc_name)
        )
        result = await db.execute(stmt)
        documents = [
            {"doc_name": row.doc_name, "chunk_count": row.chunk_count}
            for row in result.all()
        ]
        return templates.TemplateResponse(
            "documents.html",
            {
                "request": request,
                "client_id": client_id,
                "documents": documents,
                "message": str(exc),
                "error": True,
            },
        )

    n = result_info["chunks_ingested"]
    logger.info(
        "upload_document: ingested %d chunks for client=%s file=%s",
        n,
        client_id,
        file.filename,
    )
    redirect_url = (
        f"/admin/documents?client_id={client_id}"
        f"&message=Uploaded+{n}+chunk{'s' if n != 1 else ''}+from+{file.filename}"
    )
    return RedirectResponse(url=redirect_url, status_code=303)


# ---------------------------------------------------------------------------
# POST /admin/documents/delete
# ---------------------------------------------------------------------------


@router.post("/documents/delete")
async def delete_document_route(
    client_id: str = Form(...),
    doc_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Delete all chunks for a document and redirect back to the document list."""
    deleted = await delete_document(db, client_id, doc_name)
    logger.info(
        "delete_document_route: deleted %d chunks for client=%s doc=%s",
        deleted,
        client_id,
        doc_name,
    )
    redirect_url = (
        f"/admin/documents?client_id={client_id}"
        f"&message=Deleted+{doc_name}"
    )
    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/client/{client_id}/settings")
async def update_client_settings(
    client_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Save client info and schedule changes."""
    form = await request.form()

    result = await db.execute(select(Client).where(Client.client_id == client_id))
    client = result.scalar_one_or_none()
    if client is None:
        return Response("Client not found", status_code=404)

    # Client info
    name = (form.get("business_name") or "").strip()
    if name:
        client.business_name = name

    addr = (form.get("business_address") or "").strip()
    client.business_address = addr or None

    email = (form.get("owner_email") or "").strip()
    if email:
        client.owner_email = email

    # Schedule
    tz = (form.get("timezone") or "").strip()
    if tz:
        client.timezone = tz

    raw_days = form.getlist("working_days")
    if raw_days:
        try:
            client.working_days = sorted(
                {int(d) for d in raw_days if d.isdigit() and 1 <= int(d) <= 7}
            )
        except (ValueError, TypeError):
            pass  # keep existing value

    bh_start = (form.get("bh_start") or "").strip()
    bh_end = (form.get("bh_end") or "").strip()
    if bh_start and bh_end:
        client.business_hours = {"start": bh_start, "end": bh_end}

    for field in ("slot_duration_minutes", "buffer_minutes", "lead_time_minutes"):
        val = (form.get(field) or "").strip()
        if val.isdigit():
            setattr(client, field, int(val))

    await db.commit()
    return RedirectResponse(
        url=f"/admin/client/{client_id}?message=Settings+saved",
        status_code=303,
    )


@router.get("/test-calendar/{client_id}")
async def test_calendar(client_id: str, db: AsyncSession = Depends(get_db)):
    """Debug endpoint: test Google Calendar connectivity for a client."""
    from app.services.calendar import get_free_slots, CalendarError
    try:
        now = datetime.now()
        slots = await get_free_slots(db, client_id, now, now + timedelta(days=7), max_slots=3)
        return {"ok": True, "slots": [s.isoformat() for s in slots]}
    except CalendarError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Unexpected: {exc}"}


__all__ = ["router"]
