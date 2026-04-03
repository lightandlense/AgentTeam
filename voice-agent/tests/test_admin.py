"""Tests for the admin document management endpoints.

All tests use an in-memory SQLite database, mock the get_db dependency so no
real DB is required, and patch ingest_document / delete_document so no real
OpenAI calls are made.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Set required env vars before importing app (must happen before any app import)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("RETELL_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-anthropic")

from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_db(rows: list | None = None):
    """Return an async context manager that yields a mock AsyncSession."""
    rows = rows or []
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def _override():
        yield mock_session

    return _override


# ---------------------------------------------------------------------------
# GET /admin/documents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_documents_returns_200():
    """GET /admin/documents?client_id=test-client should render and return 200."""
    from app.database import get_db
    from app.routers import admin as admin_module

    app.dependency_overrides[get_db] = _make_mock_db()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/admin/documents?client_id=test-client")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert "Knowledge Base" in response.text


@pytest.mark.asyncio
async def test_get_documents_shows_empty_message():
    """When no documents exist, the page should say 'No documents ingested yet'."""
    from app.database import get_db

    app.dependency_overrides[get_db] = _make_mock_db(rows=[])
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/admin/documents?client_id=test-client")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert "No documents ingested yet" in response.text


# ---------------------------------------------------------------------------
# POST /admin/documents/upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_calls_ingest_and_redirects():
    """Uploading a valid file should call ingest_document and redirect."""
    from app.database import get_db

    mock_ingest = AsyncMock(return_value={"doc_name": "faq.txt", "chunks_ingested": 3})

    app.dependency_overrides[get_db] = _make_mock_db()
    try:
        with patch("app.routers.admin.ingest_document", mock_ingest):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    "/admin/documents/upload",
                    data={"client_id": "test-client"},
                    files={"file": ("faq.txt", b"hello world content", "text/plain")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code in (302, 303)
    assert "documents" in response.headers.get("location", "")
    mock_ingest.assert_called_once()
    call_kwargs = mock_ingest.call_args
    # positional args: (db, client_id, filename, content)
    assert call_kwargs.args[1] == "test-client"
    assert call_kwargs.args[2] == "faq.txt"


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_file_type():
    """Uploading an unsupported extension should return 200 with an error message."""
    from app.database import get_db

    mock_ingest = AsyncMock(return_value={"doc_name": "virus.exe", "chunks_ingested": 0})

    app.dependency_overrides[get_db] = _make_mock_db()
    try:
        with patch("app.routers.admin.ingest_document", mock_ingest):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/admin/documents/upload",
                    data={"client_id": "test-client"},
                    files={"file": ("virus.exe", b"bad content", "application/octet-stream")},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    assert "unsupported" in response.text.lower()
    mock_ingest.assert_not_called()


# ---------------------------------------------------------------------------
# POST /admin/documents/delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_calls_service_and_redirects():
    """Deleting a document should call delete_document and redirect."""
    from app.database import get_db

    mock_delete = AsyncMock(return_value=5)

    app.dependency_overrides[get_db] = _make_mock_db()
    try:
        with patch("app.routers.admin.delete_document", mock_delete):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    "/admin/documents/delete",
                    data={"client_id": "test-client", "doc_name": "faq.txt"},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code in (302, 303)
    mock_delete.assert_called_once()
