# Voice Agent for Local Businesses

## What This Is

A fully autonomous AI voice agent that answers inbound calls for local businesses, handles appointment booking, rescheduling, and cancellation via Google Calendar, and answers caller questions using a per-client RAG knowledge base. Delivered as a done-for-you service — Russell configures each client instance. Initially targeting salons, spas, and med spas.

## Core Value

A caller can phone a local business, book or change an appointment, and get answers to their questions — entirely handled by AI with no human staff required.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Inbound calls answered via Retell AI + Twilio phone number
- [ ] Caller can book a new appointment (fully autonomous)
- [ ] Caller can reschedule an existing appointment
- [ ] Caller can cancel an existing appointment
- [ ] Agent checks Google Calendar availability before booking
- [ ] Agent offers next 2-3 alternative slots when requested time unavailable
- [ ] If alternatives declined, agent asks caller for their available window and searches for match
- [ ] Agent answers business FAQs via RAG knowledge base (services, pricing, hours, care instructions)
- [ ] Email confirmation sent to caller after booking/reschedule/cancel
- [ ] Email notification sent to business owner after every appointment action
- [ ] Callback notification sent to business owner when no slot found or caller misunderstood
- [ ] Per-client Google OAuth (each business owns their own calendar/Gmail)
- [ ] Google OAuth tokens encrypted at rest
- [ ] Retell webhook calls verified via signature
- [ ] Admin can onboard a new client via CLI scripts
- [ ] Admin can ingest knowledge base documents (PDF, DOCX, TXT, CSV) per client
- [ ] System deployed and accessible via public URL (Railway/Render)

### Out of Scope

- Client self-service dashboard or portal — v1 is admin-managed
- SMS notifications — email only for v1
- Non-Google calendar systems — Google Calendar only for v1
- Outbound calling / appointment reminders — inbound only for v1
- Payment collection — not in scope
- Multi-location businesses — single location per client for v1

## Context

- **Delivery model:** Done-for-you service. Russell manually onboards each client.
- **Target verticals:** Salons, spas, med spas (similar appointment patterns, rich FAQ content)
- **Voice stack:** Retell AI handles STT, TTS, interruptions, turn management. Retell calls tool endpoints on the backend during live calls.
- **Phone numbers:** Twilio — one number per client, routes to Retell
- **Existing planning artifacts:** Full spec at `docs/superpowers/specs/2026-04-03-voice-agent-local-business-design.md`, implementation plan at `docs/superpowers/plans/2026-04-03-voice-agent-local-business.md`

## Constraints

- **Tech Stack:** Python (FastAPI), PostgreSQL + pgvector, Google Calendar API + Gmail API, Retell AI, Twilio, OpenAI embeddings, Claude Haiku 4.5 for RAG answers
- **Security:** Google OAuth tokens must be AES-256 encrypted at rest; Retell webhooks must be signature-verified
- **Multi-tenancy:** All clients share one backend; isolation enforced via client_id in every DB query and API call
- **Cost:** Use Claude Haiku (not Sonnet/Opus) for RAG answer generation — called on every inbound question

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Retell-native tool calling (not custom orchestrator) | Retell handles voice complexity; backend owns business logic | — Pending |
| pgvector over Pinecone | Keeps stack simple, no extra service, sufficient scale for local business KB | — Pending |
| Email-only notifications (no SMS) | Simplifies integrations; Gmail API reuses existing Google OAuth | — Pending |
| Per-client Google OAuth | Each business owns their data; no shared credentials | — Pending |
| Claude Haiku for RAG | Cost-efficient for retrieval + summarization; Sonnet not needed | — Pending |

---
*Last updated: 2026-04-03 after initialization*
