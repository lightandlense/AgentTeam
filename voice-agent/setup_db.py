import asyncio
import asyncpg
import os

# Load .env manually
env = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

# Build asyncpg-compatible URL (no +asyncpg prefix)
db_url = env["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")

from app.config import get_settings
from app.services.encryption import encrypt_token

s = get_settings()
access = input("Paste Google access token: ").strip()
refresh = input("Paste Google refresh token: ").strip()
enc_access = encrypt_token(access, s.encryption_key)
enc_refresh = encrypt_token(refresh, s.encryption_key)

async def run():
    conn = await asyncpg.connect(db_url)

    print("Running migrations...")
    for f in ["migrations/001_initial.sql", "migrations/002_calendar_config.sql", "migrations/003_appointments.sql"]:
        sql = open(f).read()
        await conn.execute(sql)
        print(f"  ran {f}")

    print("Inserting client...")
    await conn.execute("""
        INSERT INTO clients (client_id, business_name, owner_email, timezone,
                             working_days, business_hours, slot_duration_minutes,
                             buffer_minutes, lead_time_minutes)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (client_id) DO NOTHING
    """, "test-client-001", "Test Business", "test@example.com", "America/Chicago",
        [1, 2, 3, 4, 5], '{"start": "09:00", "end": "17:00"}', 60, 15, 60)

    print("Inserting OAuth tokens...")
    await conn.execute("""
        INSERT INTO oauth_tokens (client_id, encrypted_access_token, encrypted_refresh_token, token_expiry)
        VALUES ($1, $2, $3, NOW() - INTERVAL '1 hour')
        ON CONFLICT DO NOTHING
    """, "test-client-001", enc_access, enc_refresh)

    await conn.close()
    print("Done! Run python test_webhook.py to test.")

asyncio.run(run())
