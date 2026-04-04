"""
CLI to create a new client record in the voice-agent database.

Run from the voice-agent/ directory:
    python scripts/create_client.py --name "Acme Plumbing" --phone "+15555550100"
"""
import argparse
import asyncio
import sys
import uuid

sys.path.insert(0, ".")

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.client import Client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a new voice-agent client record."
    )
    parser.add_argument("--name", required=True, help="Business name (required)")
    parser.add_argument("--phone", required=True, help="Owner phone / Twilio number (required)")
    parser.add_argument("--owner-email", default="", help="Owner email address (optional)")
    parser.add_argument("--timezone", default="America/Chicago", help="Timezone (default: America/Chicago)")
    parser.add_argument("--address", default=None, help="Business address (optional)")
    return parser.parse_args()


async def create_client_async(
    client_id: str,
    name: str,
    phone: str,
    owner_email: str,
    timezone: str,
    address: str | None,
) -> None:
    async with AsyncSessionLocal() as session:
        client = Client(
            client_id=client_id,
            business_name=name,
            owner_email=owner_email,
            twilio_number=phone,
            timezone=timezone,
            business_address=address,
        )
        session.add(client)
        await session.commit()


def main() -> None:
    args = parse_args()

    if not args.name.strip():
        print("ERROR: --name must be a non-empty string", file=sys.stderr)
        sys.exit(1)

    try:
        settings = get_settings()
        if not settings.database_url:
            print("ERROR: DATABASE_URL is not set in environment", file=sys.stderr)
            sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to load settings: {exc}", file=sys.stderr)
        sys.exit(1)

    client_id = str(uuid.uuid4())

    asyncio.run(
        create_client_async(
            client_id=client_id,
            name=args.name,
            phone=args.phone,
            owner_email=args.owner_email,
            timezone=args.timezone,
            address=args.address,
        )
    )

    print(f"Created client: {client_id} ({args.name})")


if __name__ == "__main__":
    main()
