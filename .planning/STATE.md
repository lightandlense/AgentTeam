---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-04-04T16:04:36.503Z"
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 15
  completed_plans: 14
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-03)

**Core value:** A caller can phone a local business, book or change an appointment, and get answers to their questions — entirely handled by AI with no human staff required.
**Current focus:** Phase 5 — Admin and Deployment

## Current Position

Phase: 5 of 5 (Admin and Deployment)
Plan: 1 of 1 in current phase (05-01 complete)
Status: Phase 5 Plan 1 complete
Last activity: 2026-04-04 — Plan 05-01 complete: three operator CLI scripts for client onboarding (create_client.py, oauth_client.py, ingest_client.py)

Progress: [██████████████] 100% (14/14 plans)

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: 2.4 min
- Total execution time: 0.20 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 3 | 7 min | 2.3 min |
| 02-rag-knowledge-base | 3 | 10 min | 3.3 min |

**Recent Trend:**
- Last 5 plans: 01-01 (2 min), 01-02 (3 min), 01-03 (2 min), 02-01 (3 min)
- Trend: -

*Updated after each plan completion*
| Phase 02-rag-knowledge-base P02 | 3 | 2 tasks | 6 files |
| Phase 03-calendar-operations P01 | 4 | 2 tasks | 2 files |
| Phase 03-calendar-operations P02 | 5 | 2 tasks | 2 files |
| Phase 03-calendar-operations P03 | 2 | 2 tasks | 2 files |
| Phase 03-calendar-operations P04 | 3 | 2 tasks | 2 files |
| Phase 03-calendar-operations P05 | 3 | 2 tasks | 2 files |
| Phase 04-notifications-and-edge-cases P01 | 2 | 2 tasks | 3 files |
| Phase 04-notifications-and-edge-cases P02 | 4 | 2 tasks | 2 files |
| Phase 05-admin-and-deployment P01 | 5 | 2 tasks | 4 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Retell-native tool calling (not custom orchestrator): backend owns business logic, Retell handles voice
- pgvector over Pinecone: keeps stack simple, no extra service
- Per-client Google OAuth: each business owns their data, no shared credentials
- Claude Haiku for RAG: cost-efficient for retrieval + summarization on every call
- engine constructed at module import time in database.py; tests must override DATABASE_URL before importing or patch get_settings
- expire_on_commit=False on AsyncSessionLocal prevents lazy-load errors in async SQLAlchemy
- .env.example requires git add -f due to root .gitignore having .env.* wildcard
- [Phase 01-foundation]: TIMESTAMP(timezone=True) used in SQLAlchemy ORM for TIMESTAMPTZ columns — dialect-specific TIMESTAMPTZ not importable
- [Phase 01-foundation]: server_default=func.now() on all timestamp columns makes DB clock authoritative
- [Phase 01-foundation]: InvalidToken re-exported via __all__ in encryption module for single caller import point
- [Phase 01-foundation]: SECRET in test_retell_auth derived from os.environ to avoid lru_cache ordering bug when tests share process
- [Phase 01-foundation]: EXEMPT_PATHS as module-level set in middleware for O(1) path lookup and easy extension
- [Phase 02-01]: tiktoken cl100k_base used for chunking — same encoding as text-embedding-3-small, token counts match model expectations
- [Phase 02-01]: SIMILARITY_THRESHOLD = 0.75 defined in ingestion.py as canonical source — RAG query service imports from here
- [Phase 02-01]: CSV header repeated in every chunk for self-contained retrieval context
- [Phase 02-01]: delete_document() called inside ingest_document() making re-ingestion atomic (delete-then-insert)
- [Phase 02-01]: Local imports for pypdf/python-docx inside parse_file() to avoid startup cost when ingestion is idle
- [Phase 02-03]: TRANSFER_SENTINEL __TRANSFER__ returned as Retell tool result; Retell LLM prompt interprets it as cue to invoke transfer_call — no direct Retell API call needed
- [Phase 02-03]: retrieve_chunks uses sqlalchemy text() with CAST(:q_vec AS vector) for pgvector <=> operator compatibility
- [Phase 02-03]: answer_question checks TRANSFER_SENTINEL via exact match and substring to handle Haiku wrapping it in extra text
- [Phase 02-rag-knowledge-base]: EXEMPT_PREFIXES set added to retell_auth.py for prefix-based /admin/* middleware bypass
- [Phase 02-rag-knowledge-base]: POST-Redirect-GET (303) for upload/delete to prevent form resubmission
- [Phase 02-rag-knowledge-base]: Unsupported file type returns 200 re-render (not redirect) so error message visible to user
- [Phase 03-calendar-operations]: ADD COLUMN IF NOT EXISTS per-statement (no transaction block) so IF NOT EXISTS guards work correctly across repeated runs
- [Phase 03-calendar-operations]: business_hours as JSONB {start,end} HH:MM strings parallels existing hours JSONB column pattern
- [Phase 03-calendar-operations]: get_calendar_service is internal helper (not exported) — minimal public API surface
- [Phase 03-calendar-operations]: CalendarError wraps all HttpError/Exception — no stack traces leaked to callers
- [Phase 03-calendar-operations]: Test dates must use future years (2026) to avoid lead_time clamping issue in get_free_slots
- [Phase 03-03]: AppointmentError wraps CalendarError with caller-safe messages — no raw calendar errors propagate to Retell
- [Phase 03-03]: book_appointment uses 1-minute window (max_slots=1) to check exact slot availability, then 30-day window for alternatives
- [Phase 03-03]: _get_calendar_service imported as private alias in appointment.py to keep public API surface minimal
- [Phase 03-04]: Stub /tools/* endpoints removed — all calendar dispatch via single /webhook handler
- [Phase 03-04]: AppointmentError on any calendar branch returns TRANSFER_SENTINEL (not 500)
- [Phase 03-calendar-operations]: CalendarError added to except tuple in check_availability — CalendarError raised directly by get_free_slots (not wrapped in AppointmentError), must be caught at call site
- [Phase 03-calendar-operations]: find_appointment receives datetime — .date() conversion caused TypeError; appointment service expects datetime for comparison
- [Phase 04-notifications-and-edge-cases]: SMTP fields default to empty string so app starts without crashing when SMTP not configured
- [Phase 04-notifications-and-edge-cases]: Fire-and-forget email pattern: catch Exception, log error, never raise — webhook must always return
- [Phase 04-notifications-and-edge-cases]: get_settings() called inside each email function (not module level) to avoid lru_cache issues in tests
- [Phase 04-notifications-and-edge-cases]: _safe_send(coro) wrapper in retell.py catches all email exceptions — email failures never change HTTP response to Retell
- [Phase 04-notifications-and-edge-cases]: _get_client_meta wraps DB query in try/except, returns ('', '', 'UTC') on any error — prevents 500s when clients table absent in test env
- [Phase 04-notifications-and-edge-cases]: request_callback tool returns TRANSFER_SENTINEL so Retell LLM transfers call to human operator (VOICE-03)
- [Phase 05-01]: sys.path.insert(0, ".") used in CLI scripts so absolute app.* imports resolve when run from voice-agent/ directory
- [Phase 05-01]: delete+insert for oauth_tokens upsert — simpler than SQLAlchemy merge, avoids primary-key edge cases
- [Phase 05-01]: Client existence verified before OAuth browser flow — fail fast before opening browser for invalid client_id
- [Phase 05-01]: ValueError from ingest_document propagates to stderr naturally — no try/except wrapper needed in CLI

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-04-04
Stopped at: Completed 05-01-PLAN.md — three CLI scripts for operator onboarding, all 14 plans complete
Resume file: None
