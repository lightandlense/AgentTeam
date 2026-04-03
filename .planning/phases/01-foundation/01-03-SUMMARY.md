---
phase: 01-foundation
plan: 03
subsystem: api-wiring
tags: [python, fastapi, hmac, middleware, starlette, pytest-asyncio, httpx]

# Dependency graph
requires:
  - 01-01
  - 01-02
provides:
  - voice-agent/app/main.py: FastAPI app with lifespan, RetellAuthMiddleware, and /health + /retell/* routes
  - voice-agent/app/middleware/retell_auth.py: HMAC-SHA256 Starlette middleware with /health exemption
  - voice-agent/app/routers/retell.py: Router skeleton with /retell/webhook + 4 Retell tool-call stubs
  - voice-agent/tests/test_health.py: 2 tests proving /health is always 200 with no auth
  - voice-agent/tests/test_retell_auth.py: 4 tests proving HMAC auth (valid, invalid, missing, tampered)
  - voice-agent/pytest.ini: asyncio_mode = auto for all async tests
affects: [01-04, 01-05, 02-auth, 02-calendar, 02-rag, 02-retell]

# Tech tracking
tech-stack:
  added:
    - pytest-asyncio==0.25.0 (installed to environment; already in requirements.txt)
  patterns:
    - "Starlette BaseHTTPMiddleware with path exemption set for /health"
    - "HMAC-SHA256 via hmac.new + hmac.compare_digest (timing-safe)"
    - "os.environ.setdefault + lru_cache-aware secret reading in tests"
    - "ASGITransport + AsyncClient from httpx for in-process async test calls"
    - "FastAPI lifespan context manager for startup/shutdown with engine.dispose()"

key-files:
  created:
    - voice-agent/app/main.py
    - voice-agent/app/middleware/retell_auth.py
    - voice-agent/app/routers/retell.py
    - voice-agent/tests/test_health.py
    - voice-agent/tests/test_retell_auth.py
    - voice-agent/pytest.ini
  modified: []

key-decisions:
  - "SECRET in test_retell_auth derived from os.environ[RETELL_WEBHOOK_SECRET] rather than hardcoded string to avoid lru_cache ordering bug when tests run in same process"
  - "pytest-asyncio installed at runtime (not in requirements.txt venv) — was missing from environment despite being in pinned requirements"
  - "EXEMPT_PATHS as a module-level set in middleware for O(1) lookup and easy future extension"

# Metrics
duration: 2min
completed: 2026-04-03
---

# Phase 1 Plan 03: FastAPI App Wiring and HMAC Auth Summary

**FastAPI app wired with HMAC-SHA256 Retell auth middleware, /health exemption, Retell router skeleton, and 10 tests all passing (4 encryption + 2 health + 4 auth)**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-04-03T15:41:08Z
- **Completed:** 2026-04-03T15:43:04Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- `app/main.py`: FastAPI app with `asynccontextmanager` lifespan (disposes engine on shutdown), `RetellAuthMiddleware` registered, `retell_router` included, `/health` endpoint defined
- `app/middleware/retell_auth.py`: Starlette `BaseHTTPMiddleware` — reads raw body, computes HMAC-SHA256 with `get_settings().retell_webhook_secret`, uses timing-safe `hmac.compare_digest`; exempts `/health` via `EXEMPT_PATHS` set
- `app/routers/retell.py`: Router prefix `/retell` with `/webhook` entry point and four named tool-call stubs: `check_calendar_availability`, `book_appointment`, `transfer_call`, `end_call` (all return 501 in Phase 1)
- `tests/test_health.py`: 2 async tests via httpx `ASGITransport` — status 200 and body `{"status": "ok"}`, no auth required
- `tests/test_retell_auth.py`: 4 async tests — valid HMAC accepted (200), invalid signature rejected (401), missing header rejected (401), tampered body rejected (401)
- `pytest.ini`: `asyncio_mode = auto` for all async tests in the project

## Task Commits

Each task was committed atomically:

1. **Task 1: HMAC middleware, Retell router skeleton, and FastAPI app wiring** - `73fd220` (feat)
2. **Task 2: HMAC auth and health check tests with pytest-asyncio auto mode** - `9420c92` (feat)

## Files Created/Modified

- `voice-agent/app/main.py` - FastAPI app: lifespan, middleware, router, /health
- `voice-agent/app/middleware/retell_auth.py` - HMAC-SHA256 middleware with /health exemption
- `voice-agent/app/routers/retell.py` - Retell router: /webhook + 4 tool stubs
- `voice-agent/tests/test_health.py` - 2 tests for /health endpoint
- `voice-agent/tests/test_retell_auth.py` - 4 tests for HMAC authentication contract
- `voice-agent/pytest.ini` - pytest asyncio_mode = auto

## Decisions Made

- `SECRET` in `test_retell_auth.py` reads from `os.environ["RETELL_WEBHOOK_SECRET"]` rather than using a hardcoded string. The `get_settings()` lru_cache is populated by the first test module to import, so hardcoding a different value in the second module caused a HMAC mismatch. Deriving SECRET from the actual env var ensures both test modules agree on the secret in use.
- `EXEMPT_PATHS` is a module-level `set` for O(1) path lookup; easy to extend for future exempt routes.
- FastAPI lifespan used instead of deprecated `on_startup`/`on_shutdown` handlers, per FastAPI 0.93+ guidance.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pytest-asyncio not installed in environment**
- **Found during:** Task 2 (first test run)
- **Issue:** `asyncio_mode` config option unrecognized; all 6 async tests failed with "async def functions are not natively supported"
- **Fix:** Installed `pytest-asyncio==0.25.0` (already pinned in requirements.txt but not installed in active environment)
- **Files modified:** None (environment install only)
- **Commit:** N/A (env change)

**2. [Rule 1 - Bug] HMAC secret mismatch due to lru_cache + setdefault ordering**
- **Found during:** Task 2 (test run after pytest-asyncio install)
- **Issue:** `test_retell_auth.py` set `RETELL_WEBHOOK_SECRET=test-secret-key` but `test_health.py` (loaded first) set it to `test-secret`. Since `setdefault` doesn't override and `get_settings()` is lru_cached, the middleware used `test-secret` while the signature was computed with `test-secret-key` — causing `test_valid_signature_accepted` to return 401
- **Fix:** Changed `SECRET = "test-secret-key"` to `SECRET = os.environ["RETELL_WEBHOOK_SECRET"]` and aligned both test files to use the same `setdefault` value (`test-secret`)
- **Files modified:** `voice-agent/tests/test_retell_auth.py`
- **Commit:** included in `9420c92`

## Next Phase Readiness

- All 10 tests pass: `python -m pytest tests/ -v` from `voice-agent/`
- FastAPI app starts cleanly: `python -c "from app.main import app; print(app.title)"` prints `Voice Agent API`
- All 4 Retell tool endpoint stubs exist with correct names for Phase 2 implementation
- `/health` is ready for load-balancer health checks with no auth
- Middleware is ready to authenticate real Retell webhook traffic once `RETELL_WEBHOOK_SECRET` is set in production `.env`

---
*Phase: 01-foundation*
*Completed: 2026-04-03*
