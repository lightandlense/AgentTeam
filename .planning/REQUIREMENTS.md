# Requirements: Voice Agent for Local Businesses

**Defined:** 2026-04-03
**Core Value:** A caller can phone a local business, book or change an appointment, and get answers to their questions — entirely handled by AI with no human staff required.

## v1 Requirements

### Voice & Telephony

- [x] **VOICE-01**: Inbound calls answered via Retell AI agent linked to a Twilio phone number
- [x] **VOICE-02**: Retell webhook calls verified via HMAC signature before processing
- [x] **VOICE-03**: Caller can escalate to callback request if agent cannot help after 2 attempts

### Appointment Management

- [x] **APPT-01**: Caller can book a new appointment (service, date/time, name, phone, email collected)
- [x] **APPT-02**: Agent checks Google Calendar availability before confirming a booking
- [x] **APPT-03**: Agent offers next 2-3 alternative slots when requested time is unavailable
- [x] **APPT-04**: If alternatives declined, agent asks for caller's available window and searches for matching slot within 30 days
- [x] **APPT-05**: Caller can reschedule an existing appointment (looked up by name/date on Google Calendar)
- [x] **APPT-06**: Caller can cancel an existing appointment (agent confirms intent before cancelling)

### RAG Knowledge Base

- [x] **RAG-01**: Agent answers caller questions using per-client vector knowledge base (services, pricing, hours, care instructions, FAQs)
- [x] **RAG-02**: When no relevant chunks found above similarity threshold, agent offers callback rather than hallucinating
- [x] **RAG-03**: Admin can ingest documents into client knowledge base (PDF, DOCX, TXT, CSV)
- [x] **RAG-04**: Re-ingesting a document replaces old chunks without requiring full rebuild

### Notifications

- [x] **NOTIF-01**: Email confirmation sent to caller after successful booking, reschedule, or cancellation
- [x] **NOTIF-02**: Email notification sent to business owner after every appointment action (caller details + action taken)
- [x] **NOTIF-03**: Email callback request sent to business owner when no slot found or caller cannot be understood

### Multi-Tenant Client Management

- [x] **TENANT-01**: Each client has isolated data (calendar, knowledge base, OAuth tokens, config) identified by client_id
- [x] **TENANT-02**: Google OAuth tokens stored AES-256 encrypted at rest per client
- [x] **TENANT-03**: Admin can create a new client record via CLI script
- [x] **TENANT-04**: Admin can run Google OAuth flow per client via CLI script
- [x] **TENANT-05**: Admin can ingest knowledge base documents per client via CLI script

### Infrastructure

- [ ] **INFRA-01**: FastAPI backend deployed to Railway/Render with public HTTPS URL
- [x] **INFRA-02**: PostgreSQL database with pgvector extension provisioned
- [x] **INFRA-03**: Health check endpoint returns 200 OK

## v2 Requirements

### Client Management

- **MGMT-01**: Client self-service dashboard for managing services, hours, and knowledge base
- **MGMT-02**: Multi-location support (multiple calendars per client)

### Notifications

- **NOTIF-04**: SMS notifications as alternative/addition to email
- **NOTIF-05**: Automated appointment reminder outbound calls 24h before

### Telephony

- **VOICE-04**: Transfer to human staff if caller requests it
- **VOICE-05**: Voicemail detection and handling

## Out of Scope

| Feature | Reason |
|---------|--------|
| Client self-service portal | v1 is admin-configured; portal adds significant scope |
| SMS notifications | Email-only simplifies integrations; Gmail reuses existing OAuth |
| Non-Google calendar systems | Google-only for v1; multi-calendar adds complexity |
| Payment collection | Out of scope for v1 |
| Outbound/reminder calls | Inbound only for v1 |
| Multi-location businesses | Single location per client for v1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| VOICE-01 | Phase 1 | Complete |
| VOICE-02 | Phase 1 | Complete |
| VOICE-03 | Phase 4 | Complete |
| APPT-01 | Phase 3 | Complete |
| APPT-02 | Phase 3 | Complete |
| APPT-03 | Phase 3 | Complete |
| APPT-04 | Phase 3 | Complete |
| APPT-05 | Phase 3 | Complete |
| APPT-06 | Phase 3 | Complete |
| RAG-01 | Phase 2 | Complete |
| RAG-02 | Phase 2 | Complete |
| RAG-03 | Phase 2 | Complete |
| RAG-04 | Phase 2 | Complete |
| NOTIF-01 | Phase 4 | Complete |
| NOTIF-02 | Phase 4 | Complete |
| NOTIF-03 | Phase 4 | Complete |
| TENANT-01 | Phase 1 | Complete |
| TENANT-02 | Phase 1 | Complete |
| TENANT-03 | Phase 5 | Complete |
| TENANT-04 | Phase 5 | Complete |
| TENANT-05 | Phase 5 | Complete |
| INFRA-01 | Phase 5 | Pending |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-03*
*Last updated: 2026-04-03 after roadmap creation*
