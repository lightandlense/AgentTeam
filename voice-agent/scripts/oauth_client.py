"""
CLI to run per-client Google OAuth and store encrypted tokens in the database.

Run from the voice-agent/ directory:
    python scripts/oauth_client.py --client-id <uuid>
"""
import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from google_auth_oauthlib.flow import InstalledAppFlow

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.client import Client, OAuthToken
from app.services.encryption import encrypt_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Google OAuth for a voice-agent client and store encrypted tokens."
    )
    parser.add_argument("--client-id", required=True, help="Client UUID (required)")
    return parser.parse_args()


async def verify_client_exists(client_id: str) -> bool:
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.client_id == client_id)
        )
        return result.scalar_one_or_none() is not None


async def upsert_oauth_tokens(
    client_id: str,
    encrypted_access_token: str,
    encrypted_refresh_token: str,
    token_expiry,
) -> None:
    from sqlalchemy import delete

    async with AsyncSessionLocal() as session:
        # Delete existing tokens for this client, then insert fresh row
        await session.execute(
            delete(OAuthToken).where(OAuthToken.client_id == client_id)
        )
        token_row = OAuthToken(
            client_id=client_id,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            token_expiry=token_expiry,
        )
        session.add(token_row)
        await session.commit()


def main() -> None:
    args = parse_args()
    client_id = args.client_id.strip()

    if not client_id:
        print("ERROR: --client-id must be a non-empty string", file=sys.stderr)
        sys.exit(1)

    try:
        settings = get_settings()
    except Exception as exc:
        print(f"ERROR: Failed to load settings: {exc}", file=sys.stderr)
        sys.exit(1)

    if not settings.google_client_id or not settings.google_client_secret:
        print(
            "ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in environment",
            file=sys.stderr,
        )
        sys.exit(1)

    # Verify the client exists before starting the OAuth flow
    client_exists = asyncio.run(verify_client_exists(client_id))
    if not client_exists:
        print(f"ERROR: Client {client_id} not found in database", file=sys.stderr)
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8082"],
        }
    }

    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri="http://localhost:8082",
    )

    credentials = flow.run_local_server(
        port=8082,
        open_browser=True,
        prompt="consent",
        access_type="offline",
    )

    if not credentials.refresh_token:
        print(
            "WARNING: No refresh token returned. "
            "Revoke access at https://myaccount.google.com/permissions and re-run.",
            file=sys.stderr,
        )

    enc_access = encrypt_token(credentials.token or "", settings.encryption_key)
    enc_refresh = encrypt_token(credentials.refresh_token or "", settings.encryption_key)

    asyncio.run(
        upsert_oauth_tokens(
            client_id=client_id,
            encrypted_access_token=enc_access,
            encrypted_refresh_token=enc_refresh,
            token_expiry=credentials.expiry,
        )
    )

    print(f"OAuth tokens stored for client {client_id}")


if __name__ == "__main__":
    main()
