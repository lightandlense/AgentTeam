# Admin Dashboard Design

**Date:** 2026-04-04  
**Status:** Approved

## Overview

Extend the existing voice-agent admin UI with a client list home page and a per-client dashboard. The dashboard consolidates all client management into one place: business info, schedule, knowledge base, OAuth status, and tooling.

## URLs

| Route | Description |
|---|---|
| `GET /admin/` | Client list — cards for all clients |
| `GET /admin/client/{client_id}` | Per-client dashboard (single scrollable page) |
| `POST /admin/client/{client_id}/settings` | Save client info + schedule changes |

Existing document routes (`/admin/documents`, `/admin/documents/upload`, `/admin/documents/delete`) remain unchanged for backward compatibility but the documents UI is duplicated/linked from the client dashboard.

## Client List Page (`/admin/`)

- Fetches all rows from `clients` table
- Renders one card per client: business name, timezone, working days summary, link to dashboard
- No pagination needed (handful of clients)

## Client Dashboard Page (`/admin/client/{client_id}`)

Single scrollable page with five sections, each a `<form>` or read-only block:

### 1. Client Info
Editable fields: `business_name`, `business_address`, `owner_email`  
Saves via POST to `/admin/client/{client_id}/settings`

### 2. Schedule
Editable fields:
- `timezone` — text input (IANA string, e.g. `America/Denver`)
- `working_days` — checkboxes Mon–Sun (values 1–7 matching isoweekday)
- `business_hours.start` / `business_hours.end` — time inputs (HH:MM)
- `slot_duration_minutes` — number input
- `buffer_minutes` — number input
- `lead_time_minutes` — number input

Saves via POST to same endpoint. `working_days` checkboxes POST as multi-value form field, parsed server-side into `list[int]`.

### 3. Knowledge Base
Read-only summary: count of ingested documents. Link: `[Manage documents →]` goes to existing `/admin/documents?client_id={id}`. The documents page gets a `[← Back to dashboard]` link added. No duplication of forms.

### 4. OAuth Status
Read-only: shows token expiry datetime and whether it's expired.  
Link: `[Re-authorize →]` points to existing OAuth flow URL.

### 5. Tools
Button: **Test Calendar** — calls `/admin/test-calendar/{client_id}` via `fetch()`, renders result inline (slots found or error message). Single `<script>` block, no framework.

## Backend Changes

### `admin.py`

Add three handlers:
- `GET /admin/` — query all clients, render `client_list.html`
- `GET /admin/client/{client_id}` — query client + oauth_tokens, render `client_dashboard.html`
- `POST /admin/client/{client_id}/settings` — validate + update client row, redirect back to dashboard with flash message

### New Templates

- `admin/templates/client_list.html`
- `admin/templates/client_dashboard.html`

### Existing Templates

- `documents.html` — add nav link back to client dashboard (requires `client_id` in context, already available)

## Data Flow

```
GET /admin/
  → SELECT * FROM clients
  → render client_list.html

GET /admin/client/{id}
  → SELECT client + latest oauth_token
  → render client_dashboard.html

POST /admin/client/{id}/settings
  → parse + validate form fields
  → UPDATE clients SET ... WHERE client_id = ?
  → redirect GET /admin/client/{id}?message=Saved
```

## Constraints

- Plain HTML + inline CSS, no JS framework — consistent with existing admin style
- Single `<script>` block in client_dashboard.html for the Test Calendar fetch only
- No authentication on admin routes (internal tool, same as existing admin)
- `working_days` uses isoweekday convention (1=Mon, 7=Sun) throughout

## Out of Scope

- Client creation / deletion (manual SQL for now)
- Appointment list view (Google Calendar is the source of truth)
- Multi-user auth on admin routes
