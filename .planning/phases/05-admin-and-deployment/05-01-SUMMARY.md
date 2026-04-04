---
phase: 05-admin-and-deployment
plan: 01
subsystem: infra
tags: [python, argparse, asyncio, sqlalchemy, google-oauth, openai, fernet]

requires:
  - phase: 01-foundation
    provides: AsyncSessionLocal, Client ORM model, OAuthToken ORM model, encrypt_token
  - phase: 02-rag-knowledge-base
    provides: ingest_document service

provides:
  - "voice-agent/scripts/create_client.py — CLI to create Client records via DB"
  - "voice-agent/scripts/oauth_client.py — CLI to run per-client Google OAuth and store encrypted tokens"
  - "voice-agent/scripts/ingest_client.py — CLI to ingest documents into a client's knowledge base"

affects: [operator-onboarding, tenant-provisioning]

tech-stack:
  added: []
  patterns:
    - "sys.path.insert(0, '.') at top of each script for absolute app.* imports when run from voice-agent/"
    - "asyncio.run(main_async()) wrapper pattern for async DB operations in sync CLI entry points"
    - "delete+insert upsert pattern for oauth_tokens (no SQLAlchemy merge needed)"

key-files:
  created:
    - voice-agent/scripts/__init__.py
    - voice-agent/scripts/create_client.py
    - voice-agent/scripts/oauth_client.py
    - voice-agent/scripts/ingest_client.py
  modified: []

key-decisions:
  - "sys.path.insert(0, '.') used instead of relative imports — scripts run from voice-agent/ directory where .env lives"
  - "delete+insert for oauth_tokens upsert — simpler than merge, avoids SQLAlchemy merge complexity"
  - "Client existence verified before OAuth flow starts — fail fast before opening browser window"
  - "ValueError from ingest_document propagates naturally to stderr — no try/except wrapper needed for CLI"

patterns-established:
  - "CLI scripts live in voice-agent/scripts/, run from voice-agent/ directory"
  - "Fail-fast pattern: validate all args and env vars before any DB/network operations"

requirements-completed: [TENANT-03, TENANT-04, TENANT-05]

duration: 5min
completed: 2026-04-04
---

# Phase 5 Plan 01: Admin and Deployment Summary

**Three operator CLI scripts for client onboarding: create_client.py (DB record), oauth_client.py (Google Calendar tokens), ingest_client.py (knowledge base seeding)**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-04T05:41:46Z
- **Completed:** 2026-04-04T05:46:56Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Created `create_client.py` — generates uuid4 client_id, inserts Client ORM row with business name, phone, email, timezone, address
- Created `oauth_client.py` — runs InstalledAppFlow for per-client Google Calendar authorization, encrypts tokens via Fernet, upserts into oauth_tokens (delete+insert)
- Created `ingest_client.py` — reads file from disk, calls ingest_document service, prints chunk count; supports all existing types (PDF, DOCX, TXT, CSV)
- All three scripts validate required args and env vars before any I/O; fail fast with clear stderr messages

## Task Commits

Each task was committed atomically:

1. **Task 1: create_client.py — create a new client record via CLI** - `1d200b4` (feat)
2. **Task 2: oauth_client.py + ingest_client.py — OAuth flow and document ingestion CLIs** - `2331ca6` (feat)

**Plan metadata:** (pending — docs commit)

## Files Created/Modified

- `voice-agent/scripts/__init__.py` - Empty package marker so absolute imports resolve from voice-agent/
- `voice-agent/scripts/create_client.py` - CLI to create Client records; args: --name, --phone, --owner-email, --timezone, --address
- `voice-agent/scripts/oauth_client.py` - CLI to run per-client Google OAuth and store encrypted tokens; arg: --client-id
- `voice-agent/scripts/ingest_client.py` - CLI to ingest a file into a client's embeddings; args: --client-id, --file

## Decisions Made

- `sys.path.insert(0, ".")` at top of each script so `from app.config import get_settings` resolves when run from the `voice-agent/` directory where `.env` lives. No relative imports used.
- delete+insert pattern for `oauth_tokens` upsert — delete existing rows for client_id, then insert a fresh `OAuthToken` row. Simpler than SQLAlchemy `merge()` and avoids subtle primary-key issues.
- Client existence checked via DB query before the OAuth browser flow begins — fail fast rather than opening a browser window for an invalid client_id.
- `ValueError` from `ingest_document` (unsupported file type, empty content) propagates to stderr naturally via Python's default exception handling — no try/except wrapper needed for a CLI tool.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no new environment variables required. Scripts use the existing `.env` with `DATABASE_URL`, `ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `OPENAI_API_KEY`.

### Usage Reference

```bash
# From voice-agent/ directory:

# 1. Create a client
python scripts/create_client.py --name "Acme Plumbing" --phone "+15555550100"

# 2. Authorize Google Calendar for that client
python scripts/oauth_client.py --client-id <uuid-from-step-1>

# 3. Seed the knowledge base
python scripts/ingest_client.py --client-id <uuid> --file /path/to/faq.pdf
```

## Next Phase Readiness

- All three onboarding scripts are complete and functional
- Operator can now provision new clients entirely from the terminal without touching the DB directly
- Phase 5 Plan 01 is the first plan in the admin/deployment phase; subsequent plans in this phase can build on these primitives

---
*Phase: 05-admin-and-deployment*
*Completed: 2026-04-04*
