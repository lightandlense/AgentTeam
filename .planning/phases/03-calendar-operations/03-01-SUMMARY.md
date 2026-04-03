---
phase: 03-calendar-operations
plan: "01"
subsystem: database
tags: [postgres, sqlalchemy, orm, migrations, postgresql-array, jsonb]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: clients table schema, SQLAlchemy Base, ORM conventions
  - phase: 02-rag-knowledge-base
    provides: 23 passing tests baseline, existing ORM models
provides:
  - "Per-client calendar config columns: working_days, business_hours, slot_duration_minutes, buffer_minutes, lead_time_minutes"
  - "Idempotent SQL migration 002_calendar_config.sql"
  - "Client ORM model updated with all 5 calendar config fields"
affects:
  - 03-calendar-operations (plans 02+) — all calendar ops read these columns
  - calendar service, availability checks, booking, slot search

# Tech tracking
tech-stack:
  added: [sqlalchemy.ARRAY]
  patterns: [ADD COLUMN IF NOT EXISTS idempotent migration, ARRAY(Integer) mapped column, server_default string literals for PostgreSQL types]

key-files:
  created:
    - voice-agent/migrations/002_calendar_config.sql
  modified:
    - voice-agent/app/models/client.py

key-decisions:
  - "ADD COLUMN IF NOT EXISTS per-statement (no transaction block) so IF NOT EXISTS guards work correctly across repeated runs"
  - "ARRAY(Integer) for working_days using ISO weekday numbers 1=Mon...7=Sun, default Mon-Fri {1,2,3,4,5}"
  - "business_hours as JSONB with {start, end} HH:MM strings, not separate columns — matches existing hours column pattern"
  - "server_default string form (not Python default) for all new columns — consistent with existing ORM column style"

patterns-established:
  - "ALTER TABLE migration pattern: one ADD COLUMN IF NOT EXISTS per statement, no wrapping transaction block"
  - "ARRAY columns: use ARRAY(Integer) type from sqlalchemy core, not dialect-specific, with server_default PostgreSQL literal"

requirements-completed: [APPT-02]

# Metrics
duration: 4min
completed: 2026-04-03
---

# Phase 3 Plan 01: Calendar Config Schema Summary

**Five per-client calendar config columns added to clients table via idempotent SQL migration and Client SQLAlchemy ORM model**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-03T00:00:00Z
- **Completed:** 2026-04-03T00:04:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created idempotent SQL migration `002_calendar_config.sql` adding 5 calendar config columns with correct PostgreSQL defaults
- Updated `Client` ORM model with all 5 fields using correct SQLAlchemy types (ARRAY, JSONB, Integer)
- Added `ARRAY` import to sqlalchemy imports line
- All 28 existing tests continue to pass with zero changes required

## Task Commits

Each task was committed atomically:

1. **Task 1: SQL migration — add calendar config columns** - `b6b4fd4` (feat)
2. **Task 2: Update Client ORM model with calendar config fields** - `d537a7e` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified
- `voice-agent/migrations/002_calendar_config.sql` - Idempotent ALTER TABLE migration adding 5 calendar config columns
- `voice-agent/app/models/client.py` - Client ORM extended with working_days, business_hours, slot_duration_minutes, buffer_minutes, lead_time_minutes

## Decisions Made
- No transaction block wrapping the ALTER statements — IF NOT EXISTS guards only work correctly as individual statements in PostgreSQL
- `ARRAY(Integer)` from `sqlalchemy` (not dialect-specific) for `working_days`; server_default uses PostgreSQL array literal `{1,2,3,4,5}`
- `business_hours` stored as JSONB `{"start": "09:00", "end": "17:00"}` — parallels existing `hours` JSONB column pattern, avoids proliferating scalar columns for a logical unit
- All new columns use `server_default` string form (not Python `default=`) — consistent with all existing columns in the model

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Run the migration against your PostgreSQL instance:
```bash
psql $DATABASE_URL -f voice-agent/migrations/002_calendar_config.sql
```

## Next Phase Readiness
- All 5 calendar config columns exist in both SQL schema and ORM model
- Client rows seeded before Phase 3 will get default values automatically (Mon-Fri, 9-5, 60-min slots, 0 buffer, 60-min lead time)
- Calendar service (03-02+) can read per-client config directly from the clients row
- No blockers

---
*Phase: 03-calendar-operations*
*Completed: 2026-04-03*
