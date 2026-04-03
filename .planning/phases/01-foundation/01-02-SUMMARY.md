---
phase: 01-foundation
plan: 02
subsystem: db-schema
tags: [python, sqlalchemy, pgvector, postgresql, fernet, encryption, migrations]

# Dependency graph
requires:
  - 01-01
provides:
  - voice-agent/migrations/001_initial.sql: DDL for clients, oauth_tokens, embeddings with pgvector ivfflat index
  - voice-agent/app/models/client.py: SQLAlchemy 2.0 ORM models (Client, OAuthToken, Embedding)
  - voice-agent/app/services/encryption.py: Fernet encrypt/decrypt for OAuth token storage
  - voice-agent/tests/test_encryption.py: 4 passing tests proving encryption contract
affects: [01-03, 01-04, 01-05, 02-auth, 02-calendar, 02-rag]

# Tech tracking
tech-stack:
  added:
    - pgvector==0.3.6 (installed; already in requirements.txt)
    - asyncpg==0.30.0 (installed; already in requirements.txt)
  patterns:
    - "SQLAlchemy 2.0 mapped_column style with Mapped[] type annotations"
    - "server_default=func.now() for TIMESTAMPTZ columns so DB clock is authoritative"
    - "pgvector.sqlalchemy.Vector(1536) for cosine similarity embeddings column"
    - "Fernet symmetric encryption for OAuth token storage in PostgreSQL TEXT columns"
    - "tests/conftest.py sys.path insert for app.* imports during pytest runs"

key-files:
  created:
    - voice-agent/migrations/001_initial.sql
    - voice-agent/app/models/client.py
    - voice-agent/app/services/encryption.py
    - voice-agent/tests/test_encryption.py
    - voice-agent/tests/conftest.py
  modified: []

key-decisions:
  - "Used sqlalchemy.TIMESTAMP(timezone=True) instead of TIMESTAMPTZ dialect type — TIMESTAMPTZ is not a direct SQLAlchemy import"
  - "server_default=func.now() on all timestamp columns makes DB clock authoritative rather than Python-side datetime.utcnow()"
  - "InvalidToken re-exported from encryption module via __all__ so callers import from a single location"

# Metrics
duration: 3min
completed: 2026-04-03
---

# Phase 1 Plan 02: Database Schema and Encryption Summary

**PostgreSQL schema (clients/oauth_tokens/embeddings) with pgvector ivfflat index and Fernet encryption service for OAuth token storage — 4 tests all passing**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-03T15:36:06Z
- **Completed:** 2026-04-03T15:38:43Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `migrations/001_initial.sql`: complete DDL with `CREATE EXTENSION vector`, three tables, and `ivfflat (embedding vector_cosine_ops) WITH (lists = 100)` index for cosine similarity search
- `app/models/client.py`: SQLAlchemy 2.0 `mapped_column` ORM models for Client, OAuthToken, and Embedding; `Vector(1536)` column via pgvector; all foreign keys with `ON DELETE CASCADE`
- `app/services/encryption.py`: three-function Fernet API (`generate_key`, `encrypt_token`, `decrypt_token`); `InvalidToken` re-exported for callers
- `tests/test_encryption.py`: 4 pytest tests proving ciphertext differs from plaintext, round-trip recovery, wrong-key raises `InvalidToken`, and key length == 44
- `tests/conftest.py`: sys.path insert enabling `app.*` imports in pytest without package installation

## Task Commits

Each task was committed atomically:

1. **Task 1: SQL migration and SQLAlchemy ORM models** — `3be923c` (feat)
2. **Task 2: Encryption service and tests** — `6ee5a06` (feat)

## Files Created/Modified

- `voice-agent/migrations/001_initial.sql` — DDL for clients, oauth_tokens, embeddings + pgvector ivfflat index
- `voice-agent/app/models/client.py` — SQLAlchemy 2.0 ORM: Client, OAuthToken, Embedding mapped to exact SQL table names
- `voice-agent/app/services/encryption.py` — Fernet encrypt/decrypt/generate_key with InvalidToken re-export
- `voice-agent/tests/test_encryption.py` — 4 tests: ciphertext != plaintext, round-trip, wrong-key, valid key length
- `voice-agent/tests/conftest.py` — sys.path bootstrap for test imports

## Decisions Made

- `TIMESTAMP(timezone=True)` used in SQLAlchemy ORM (not `TIMESTAMPTZ`) — the dialect-specific name is not importable directly; `TIMESTAMP(timezone=True)` maps to `TIMESTAMPTZ` in PostgreSQL
- `server_default=func.now()` on all timestamp columns so the database clock is authoritative
- `InvalidToken` re-exported via `__all__` in encryption module to give callers a single import point

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TIMESTAMPTZ not importable from sqlalchemy.dialects.postgresql**
- **Found during:** Task 1 (model import verification)
- **Issue:** `from sqlalchemy.dialects.postgresql import TIMESTAMPTZ` raises `ImportError`; SQLAlchemy exposes this as `sqlalchemy.TIMESTAMP(timezone=True)`
- **Fix:** Changed import to `from sqlalchemy import TIMESTAMP` and used `TIMESTAMP(timezone=True)` for all timestamp columns — produces identical DDL in PostgreSQL
- **Files modified:** `voice-agent/app/models/client.py`
- **Commit:** included in `3be923c`

## Next Phase Readiness

- Plan 01-03 and beyond can import `Client`, `OAuthToken`, `Embedding` from `app.models.client`
- Phase 2 RAG can use the `embeddings` table and ivfflat index immediately
- Phase 2 Calendar can store encrypted tokens via `encrypt_token` / `decrypt_token`
- Run migration against a live database: `psql $DATABASE_URL -f voice-agent/migrations/001_initial.sql`

---
*Phase: 01-foundation*
*Completed: 2026-04-03*

## Self-Check: PASSED

- FOUND: voice-agent/migrations/001_initial.sql
- FOUND: voice-agent/app/models/client.py
- FOUND: voice-agent/app/services/encryption.py
- FOUND: voice-agent/tests/test_encryption.py
- FOUND: .planning/phases/01-foundation/01-02-SUMMARY.md
- Commit 3be923c verified (Task 1)
- Commit 6ee5a06 verified (Task 2)
