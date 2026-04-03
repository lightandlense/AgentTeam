---
phase: 02-rag-knowledge-base
plan: 01
subsystem: api
tags: [openai, embeddings, pypdf, python-docx, tiktoken, pgvector, sqlalchemy, ingestion]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Embedding SQLAlchemy model, AsyncSession, get_settings(), openai_api_key config

provides:
  - ingest_document() async function — parse/embed/store pipeline for PDF, DOCX, TXT, CSV
  - delete_document() async function — clean removal of all chunks for a (client_id, doc_name) pair
  - chunk_text() — tiktoken-based 400-token window chunker with 80-token overlap
  - chunk_csv() — CSV row-grouping chunker (10 rows per chunk, header repeated)
  - parse_file() — extension-dispatching file parser with 10MB size guard
  - SIMILARITY_THRESHOLD = 0.75 — canonical value for RAG query service
  - 8 unit tests, all passing with no real OpenAI or DB calls

affects: [02-rag-knowledge-base, 02-02-api-endpoints, 02-03-rag-query, 03-booking]

# Tech tracking
tech-stack:
  added: [pypdf==5.1.0, python-docx==1.1.2, tiktoken==0.8.0]
  patterns:
    - delete-then-insert re-ingestion pattern for idempotent document updates
    - tiktoken cl100k_base encoding for token-accurate chunking consistent with OpenAI models
    - header-per-chunk CSV pattern for self-contained retrieval context
    - EMBED_BATCH_SIZE=100 OpenAI batching for safe throughput within API limits
    - local imports for heavy parsers (pypdf, docx) to keep startup cost near zero

key-files:
  created:
    - voice-agent/app/services/ingestion.py
    - voice-agent/tests/test_ingestion.py
  modified:
    - voice-agent/requirements.txt

key-decisions:
  - "tiktoken cl100k_base used for chunking — same encoding as text-embedding-3-small, ensuring token counts match embedding model expectations"
  - "Local imports for pypdf and python-docx inside parse_file() — avoids import cost at startup when ingestion is not called"
  - "SIMILARITY_THRESHOLD = 0.75 defined in ingestion.py as canonical source — RAG query service will import it from here"
  - "CSV header repeated in every chunk — each chunk is self-contained for retrieval without needing adjacent chunks"
  - "delete-then-insert re-ingestion: delete_document() is called inside ingest_document() before bulk insert, so re-ingestion is atomic from caller's perspective"

patterns-established:
  - "Chunking pattern: token-window with overlap for text, row-group with repeated header for CSV"
  - "Embedding pattern: EMBED_BATCH_SIZE=100 batching with flat list return aligned to input"
  - "Re-ingestion pattern: delete_document() then bulk add() then commit() — no partial state"

requirements-completed: [RAG-03, RAG-04]

# Metrics
duration: 3min
completed: 2026-04-03
---

# Phase 2 Plan 01: Document Ingestion Service Summary

**PDF/DOCX/TXT/CSV parsing into tiktoken chunks, OpenAI text-embedding-3-small embeddings, PostgreSQL vector storage with idempotent delete-then-insert re-ingestion**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-03T18:16:47Z
- **Completed:** 2026-04-03T18:19:08Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Document ingestion service with multi-format parsing (PDF, DOCX, TXT, CSV) and 10MB size guard
- Token-accurate chunking using tiktoken cl100k_base (400-token windows, 80-token overlap) plus CSV row grouping
- OpenAI text-embedding-3-small integration with EMBED_BATCH_SIZE=100 batching
- Idempotent re-ingestion via delete-then-insert using SQLAlchemy async delete
- 8 unit tests passing with all external dependencies mocked — no real OpenAI or DB calls

## Task Commits

Each task was committed atomically:

1. **Task 1: Add parsing dependencies and write ingestion service** - `0180655` (feat)
2. **Task 2: Write ingestion unit tests** - `020c643` (test)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `voice-agent/app/services/ingestion.py` - Full ingestion service: parse_file, chunk_text, chunk_csv, chunk_file, embed_chunks, delete_document, ingest_document, SIMILARITY_THRESHOLD
- `voice-agent/tests/test_ingestion.py` - 8 unit tests covering all public functions with mocked external deps
- `voice-agent/requirements.txt` - Added pypdf==5.1.0, python-docx==1.1.2, tiktoken==0.8.0

## Decisions Made

- tiktoken cl100k_base encoding chosen for chunking to match text-embedding-3-small's tokenizer — ensures chunk token counts accurately reflect what the model sees
- Heavy parser imports (pypdf, docx) are local to parse_file() to avoid startup cost when ingestion is not active
- SIMILARITY_THRESHOLD defined here as canonical source of truth — RAG query service in plan 02-03 will import it from ingestion.py
- CSV header repeated in every chunk so each chunk is self-contained for vector retrieval
- delete_document() called inside ingest_document() making re-ingestion atomic from the caller's perspective

## Deviations from Plan

### Minor Deviation: 8 tests instead of 7

The plan specified 7 tests. During implementation, `chunk_csv` had two distinct testable behaviors — row grouping count and header inclusion — which were naturally separated into two tests for clarity. The plan's "Test: chunk_csv groups rows" was split into:
- `test_chunk_csv_groups_rows` (verifies len == 3)
- `test_chunk_csv_includes_header_in_every_chunk` (verifies header present in each chunk)

This is an improvement, not a scope deviation. All 7 originally specified behaviors are covered; one was split for clarity.

### Issue: Missing pip packages

- **Found during:** Task 1 verification
- **Issue:** pypdf, python-docx, tiktoken not yet installed in the environment
- **Fix:** Rule 3 auto-fix — ran `pip install pypdf==5.1.0 python-docx==1.1.2 tiktoken==0.8.0`
- **Verification:** Import check `python -c "from app.services.ingestion import ..."` passed after install

---

**Total deviations:** 1 minor (extra test for better coverage), 1 auto-fix (missing pip packages)
**Impact on plan:** No scope creep. Extra test improves coverage. Pip install is expected bootstrapping.

## Issues Encountered

None beyond the pip install bootstrap — plan executed cleanly once dependencies were present.

## User Setup Required

None - no external service configuration required for this plan. OpenAI API key was already defined in Phase 1's .env setup.

## Next Phase Readiness

- ingestion.py is ready for Phase 2 Plan 02 (upload API endpoint) to call ingest_document() and delete_document()
- SIMILARITY_THRESHOLD is available for import by plan 02-03 (RAG query service)
- All 18 tests pass — no regressions from Phase 1

---
*Phase: 02-rag-knowledge-base*
*Completed: 2026-04-03*
