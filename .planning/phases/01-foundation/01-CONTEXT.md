# Phase 1: Foundation - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Set up the FastAPI backend project from scratch: directory scaffold, dependencies, database schema with multi-tenant isolation, encrypted OAuth token storage, and Retell webhook HMAC verification. The app starts locally, connects to PostgreSQL with pgvector, and is ready for feature layers (RAG, calendar, notifications) in later phases.

No call logic, no RAG, no calendar, no notifications in this phase — pure infrastructure.

</domain>

<decisions>
## Implementation Decisions

### Target business (first client)
- **Galvan Appliance Repair & Home Services** — appliance repair bookings (not a salon/spa)
- AI agent persona: **Joe** — friendly, bilingual (English + Spanish) receptionist
- Collects: first name, last name, phone number, preferred date/time, reason for visit
- Transfer call condition: caller unhappy/frustrated or question not in knowledge base
- This informs the `clients` table fields and test fixtures — use Galvan as the reference client in tests

### Tech stack (locked from superpowers plan)
- Python 3.11, FastAPI, SQLAlchemy 2.0 async (mapped_column style), asyncpg
- Pydantic Settings for config (loads from `.env`)
- `cryptography` library — Fernet (AES-128 in CBC mode with HMAC, adequate for token storage)
- pgvector extension on PostgreSQL (vector dimension: 1536 for OpenAI `text-embedding-3-small`)
- pytest + pytest-asyncio for tests; aiosqlite for in-memory test DB

### Project structure (locked from superpowers plan)
- Feature-based layout: `app/routers/`, `app/services/`, `app/models/`, `app/middleware/`
- Entry point: `app/main.py` (FastAPI app, router registration, lifespan)
- Admin scripts in `admin/` (not inside the app package)
- Migrations as raw SQL files in `migrations/` (not Alembic in Phase 1)

### Database schema (locked from superpowers plan)
Three tables:
1. `clients` — primary key `client_id TEXT`, stores business config (name, address, timezone, owner_email, twilio_number, retell_agent_id, services JSONB, hours JSONB)
2. `oauth_tokens` — FK to clients, stores `encrypted_access_token`, `encrypted_refresh_token`, `token_expiry`
3. `embeddings` — FK to clients, stores `doc_name`, `chunk_index`, `content`, `embedding vector(1536)` — ivfflat index for cosine similarity

Multi-tenant isolation: `client_id` column on every table + application-layer filtering (no Postgres RLS in Phase 1)

### Retell webhook authentication
- Dedicated middleware: `app/middleware/retell_auth.py`
- Verifies HMAC-SHA256 signature from `X-Retell-Signature` header against `RETELL_WEBHOOK_SECRET`
- Returns HTTP 401 on invalid signature, passes through on valid
- Applied globally to all routes except `/health`

### Health check
- `GET /health` returns `{"status": "ok"}` with HTTP 200
- No auth required
- Used by Railway/Render for deployment health checks

### Local dev environment
- Bare Python: `pip install -r requirements.txt`
- Local PostgreSQL with pgvector extension (not Docker — Russell runs Postgres locally)
- Config via `.env` file (`.env.example` committed, `.env` gitignored)
- App started with: `uvicorn app.main:app --reload`

### Encryption approach
- Fernet symmetric encryption for OAuth tokens (access + refresh)
- `ENCRYPTION_KEY` env var holds the Fernet key (generated once via `admin/oauth_setup.py`)
- Functions: `generate_key()`, `encrypt_token(plaintext, key)`, `decrypt_token(ciphertext, key)`
- Wrong key raises `InvalidToken` — test verifies this

### Claude's Discretion
- Exact ivfflat index `lists` parameter (plan uses 100 — Claude can adjust based on expected data volume)
- Async session factory pattern details (async_sessionmaker already chosen)
- Test fixture structure for mock DB beyond what's specified in the plan

</decisions>

<specifics>
## Specific Ideas

- Retell calls our tool endpoints during live calls (webhook-style, not WebSocket in Phase 1)
- Tool names Retell expects: `check_calendar_availability`, `book_appointment`, `transfer_call`, `end_call` — these are NOT implemented in Phase 1 but the router skeleton should be named to match
- Joe (the agent) confirms collected info back to caller before booking — backend doesn't enforce this, it's a Retell prompt behavior
- "No client-facing dashboard in v1" — management entirely via admin CLI scripts

### Key env vars (from superpowers plan)
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/voiceagent
ENCRYPTION_KEY=           # Fernet key
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
RETELL_API_KEY=
RETELL_WEBHOOK_SECRET=
```

</specifics>

<deferred>
## Deferred Ideas

- Alembic migrations — Phase 1 uses raw SQL; Alembic can be added when schema evolves
- Docker Compose for local dev — not needed yet, Russell runs Postgres locally
- Per-client API key auth for direct backend calls — noted in design spec, deferred past Phase 1
- SMS notifications — out of scope v1
- Client self-service dashboard — out of scope v1
- Bilingual (Spanish) responses from the agent — Retell/prompt concern, not backend

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-04-03*
