"""Tests for the RAG query service and Retell webhook dispatch.

All OpenAI, Anthropic, and database calls are mocked — no real API calls.
"""

import hashlib
import hmac
import json
import os
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

from app.services.rag import TRANSFER_SENTINEL, answer_question  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SECRET = os.environ["RETELL_WEBHOOK_SECRET"]
WEBHOOK_URL = "/retell/webhook"


def _make_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _fake_embedding() -> list[float]:
    return [0.1] * 1536


# ---------------------------------------------------------------------------
# Unit tests for answer_question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_question_no_chunks_returns_transfer():
    """When retrieve_chunks returns [], answer_question returns TRANSFER_SENTINEL
    without ever calling generate_answer."""
    mock_db = MagicMock()

    # Fake embed response
    fake_embed = MagicMock()
    fake_embed.data = [MagicMock(embedding=_fake_embedding())]

    with (
        patch("app.services.rag.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve,
        patch("app.services.rag.generate_answer", new_callable=AsyncMock) as mock_generate,
        patch("app.services.rag.openai.AsyncOpenAI") as mock_oai_cls,
    ):
        mock_oai_instance = AsyncMock()
        mock_oai_instance.embeddings.create = AsyncMock(return_value=fake_embed)
        mock_oai_cls.return_value = mock_oai_instance

        mock_retrieve.return_value = []

        result = await answer_question(mock_db, "test-client", "What are your prices?")

    assert result == TRANSFER_SENTINEL
    mock_generate.assert_not_called()


@pytest.mark.asyncio
async def test_answer_question_with_chunks_returns_answer():
    """When retrieve_chunks returns content, answer_question returns the generated answer."""
    mock_db = MagicMock()
    fake_chunks = [
        "We charge $80/hour for labor.",
        "Parts are billed at cost plus 20%.",
    ]
    expected_answer = "Our labor rate is $80 per hour and parts are billed at cost plus 20%."

    fake_embed = MagicMock()
    fake_embed.data = [MagicMock(embedding=_fake_embedding())]

    with (
        patch("app.services.rag.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve,
        patch("app.services.rag.generate_answer", new_callable=AsyncMock) as mock_generate,
        patch("app.services.rag.openai.AsyncOpenAI") as mock_oai_cls,
    ):
        mock_oai_instance = AsyncMock()
        mock_oai_instance.embeddings.create = AsyncMock(return_value=fake_embed)
        mock_oai_cls.return_value = mock_oai_instance

        mock_retrieve.return_value = fake_chunks
        mock_generate.return_value = expected_answer

        result = await answer_question(mock_db, "test-client", "How much do you charge?")

    assert result == expected_answer


@pytest.mark.asyncio
async def test_answer_question_haiku_transfer_returns_sentinel():
    """When generate_answer returns __TRANSFER__, answer_question propagates it."""
    mock_db = MagicMock()

    fake_embed = MagicMock()
    fake_embed.data = [MagicMock(embedding=_fake_embedding())]

    with (
        patch("app.services.rag.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve,
        patch("app.services.rag.generate_answer", new_callable=AsyncMock) as mock_generate,
        patch("app.services.rag.openai.AsyncOpenAI") as mock_oai_cls,
    ):
        mock_oai_instance = AsyncMock()
        mock_oai_instance.embeddings.create = AsyncMock(return_value=fake_embed)
        mock_oai_cls.return_value = mock_oai_instance

        mock_retrieve.return_value = ["Some content"]
        mock_generate.return_value = TRANSFER_SENTINEL

        result = await answer_question(mock_db, "test-client", "some question")

    assert result == TRANSFER_SENTINEL


# ---------------------------------------------------------------------------
# Integration tests — Retell webhook dispatch (mocked service layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retell_webhook_dispatches_answer_question():
    """Webhook correctly dispatches answer_question tool calls and returns result."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    body_dict = {
        "event": "tool_call",
        "tool_call_id": "call_123",
        "name": "answer_question",
        "arguments": {"client_id": "test-client", "question": "What are your hours?"},
    }
    body = json.dumps(body_dict).encode()
    sig = _make_signature(body, SECRET)

    with patch(
        "app.routers.retell.answer_question",
        new_callable=AsyncMock,
        return_value="We are open 9am-5pm Monday through Friday.",
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                WEBHOOK_URL,
                content=body,
                headers={
                    "X-Retell-Signature": sig,
                    "Content-Type": "application/json",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["tool_call_id"] == "call_123"
    assert data["result"] == "We are open 9am-5pm Monday through Friday."


@pytest.mark.asyncio
async def test_retell_webhook_ignores_non_tool_call_events():
    """Webhook returns {status: received} for non-tool-call events."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    body = json.dumps({"event": "call_started"}).encode()
    sig = _make_signature(body, SECRET)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            WEBHOOK_URL,
            content=body,
            headers={
                "X-Retell-Signature": sig,
                "Content-Type": "application/json",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "received"}
