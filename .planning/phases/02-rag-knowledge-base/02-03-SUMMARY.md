---
phase: 02-rag-knowledge-base
plan: "03"
subsystem: api
tags: [rag, openai, anthropic, pgvector, claude-haiku, embeddings, retell]

# Dependency graph
requires:
  - phase: 02-01
    provides: EMBED_MODEL, SIMILARITY_THRESHOLD constants and Embedding ORM model
  - phase: 01-foundation
    provides: AsyncSession, get_db, get_settings, HMAC webhook middleware

provides:
  - answer_question() async function in app/services/rag.py
  - retrieve_chunks() — pgvector cosine similarity query with threshold filter
  - generate_answer() — Claude Haiku conversational answer generation
  - Updated Retell webhook handler that dispatches answer_question tool calls

affects:
  - 02-04 (if any document management UI plan)
  - phase 3 (appointment booking — same webhook dispatch pattern)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - TRANSFER_SENTINEL string "__TRANSFER__" used as fallback signal from RAG to Retell
    - pgvector cosine similarity filter using (1 - (embedding <=> vec)) >= threshold pattern
    - Retell tool call dispatch pattern in webhook handler (check event type, route by name)

key-files:
  created:
    - voice-agent/app/services/rag.py
    - voice-agent/tests/test_rag.py
  modified:
    - voice-agent/app/routers/retell.py

key-decisions:
  - "TRANSFER_SENTINEL __TRANSFER__ returned to Retell; Retell agent's LLM prompt interprets it as a cue to invoke transfer_call — no direct Retell API call needed"
  - "retrieve_chunks uses sqlalchemy text() with CAST(:q_vec AS vector) for pgvector operator compatibility"
  - "answer_question checks TRANSFER_SENTINEL both exactly and via 'in' to catch cases where Haiku wraps it in extra text"

patterns-established:
  - "Retell webhook pattern: check event != tool_call first, then route by tool name"
  - "RAG service pattern: embed -> retrieve with threshold -> generate or sentinel"

requirements-completed:
  - RAG-01
  - RAG-02

# Metrics
duration: 4min
completed: "2026-04-03"
---

# Phase 2 Plan 03: RAG Query Service Summary

**RAG query service using OpenAI embeddings + pgvector retrieval + Claude Haiku generation, wired into Retell webhook with __TRANSFER__ sentinel fallback**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-03T18:19:11Z
- **Completed:** 2026-04-03T18:23:25Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created `app/services/rag.py` with full RAG pipeline: embed question with OpenAI, retrieve top-5 similar chunks via pgvector with 0.75 cosine similarity threshold, generate conversational phone-style answer with Claude Haiku
- Updated Retell webhook router to dispatch `answer_question` tool calls to RAG service and return structured `{tool_call_id, result}` response
- Added 5 tests covering both RAG paths (answer and transfer), Haiku transfer passthrough, webhook dispatch, and non-tool-call event handling
- All 23 tests pass (18 prior + 5 new)

## Task Commits

1. **Task 1: RAG query service and Retell webhook wiring** - `8f4329e` (feat)
2. **Task 2: RAG service tests** - `c36f297` (test)

**Plan metadata:** (forthcoming docs commit)

## Files Created/Modified
- `voice-agent/app/services/rag.py` — answer_question(), retrieve_chunks(), generate_answer() with TRANSFER_SENTINEL fallback
- `voice-agent/app/routers/retell.py` — Updated webhook handler dispatching answer_question tool calls
- `voice-agent/tests/test_rag.py` — 5 async tests with fully mocked OpenAI/Anthropic/DB

## Decisions Made
- TRANSFER_SENTINEL `__TRANSFER__` string is returned to Retell as the tool result; Retell's LLM interprets it as a cue to invoke its `transfer_call` tool. Eliminates need for a direct Retell transfer API call from the webhook.
- Used `sqlalchemy.text()` with `CAST(:q_vec AS vector)` for the pgvector `<=>` operator since it isn't natively supported in SQLAlchemy ORM.
- `answer_question` checks both exact equality and substring match for TRANSFER_SENTINEL to handle cases where Haiku wraps it in surrounding text.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. (Real API keys needed at runtime but no new config steps beyond what Phase 1 and 02-01 established.)

## Next Phase Readiness

- RAG query pipeline complete: callers can get answers grounded in ingested business documents
- Both answer path (conversational reply) and transfer path (__TRANSFER__ sentinel) verified by tests
- Retell webhook dispatch pattern established — Phase 3 appointment booking can follow the same routing pattern
- No blockers

## Self-Check: PASSED

- voice-agent/app/services/rag.py: FOUND
- voice-agent/app/routers/retell.py: FOUND
- voice-agent/tests/test_rag.py: FOUND
- .planning/phases/02-rag-knowledge-base/02-03-SUMMARY.md: FOUND
- Commit 8f4329e: FOUND
- Commit c36f297: FOUND

---
*Phase: 02-rag-knowledge-base*
*Completed: 2026-04-03*
