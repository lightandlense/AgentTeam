import hashlib
import hmac
import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("RETELL_WEBHOOK_SECRET", "test-secret")

from app.main import app  # noqa: E402

# Must match RETELL_WEBHOOK_SECRET env var used above
SECRET = os.environ["RETELL_WEBHOOK_SECRET"]
WEBHOOK_URL = "/retell/webhook"


def make_signature(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_valid_signature_accepted():
    body = b'{"event": "call_started", "client_id": "galvan"}'
    sig = make_signature(body, SECRET)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            WEBHOOK_URL,
            content=body,
            headers={"X-Retell-Signature": sig, "Content-Type": "application/json"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_signature_rejected():
    body = b'{"event": "call_started"}'
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            WEBHOOK_URL,
            content=body,
            headers={"X-Retell-Signature": "invalid-signature", "Content-Type": "application/json"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_signature_rejected():
    body = b'{"event": "call_started"}'
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            WEBHOOK_URL,
            content=body,
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tampered_body_rejected():
    """Sign original body, then send different body — should fail HMAC."""
    original_body = b'{"event": "call_started"}'
    tampered_body = b'{"event": "call_started", "injected": true}'
    sig = make_signature(original_body, SECRET)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            WEBHOOK_URL,
            content=tampered_body,
            headers={"X-Retell-Signature": sig, "Content-Type": "application/json"},
        )
    assert response.status_code == 401
