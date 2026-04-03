# Phase 3: Calendar Operations - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Full appointment lifecycle — booking, rescheduling, and cancellation — handled autonomously by the voice agent via Google Calendar. Callers interact verbally; the agent collects all required info, confirms before committing, and hands off to the team when it can't resolve. Email notifications and callback escalation are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Slot Offering Behavior
- Offer 2 alternatives when a requested time is taken
- Read both sequentially: "I have Tuesday at 2pm or Wednesday at 10am — which works?"
- If caller rejects both: ask for a preferred window ("What days or times generally work for you?") then search within it
- Search window when given a preference: 30 days forward
- Always search forward from requested time — no "nearest before/after" logic
- Offer next 2 available slots regardless of day (no same-day preference)
- Slot format: day + time ("Tuesday at 2pm") — no duration mentioned
- If no slots found within the caller's 30-day preferred window: transfer to the team

### Caller Identity and Booking Intake
- Reschedule/cancel lookup: name + appointment date
- Multiple appointments matching same name + date: read them out and ask which one ("I see two for John Smith on Thursday — one at 10am and one at 2pm. Which is yours?")
- No appointment found: ask once to confirm details, then transfer if still not found
- New booking collects 6 required fields in this order: name → phone → email → address → problem description → special access notes (gate codes, etc.)
- Problem description: open question ("Can you briefly describe the issue?")
- All 6 fields are required — agent won't book without complete info
- If caller refuses a required field: ask once more politely ("We do need that to send you a confirmation — if you'd prefer, I can connect you with someone"), then transfer

### Confirmation Flow
- Final booking confirmation: agent reads back date, time, and name — asks "shall I go ahead and book that?" before committing to Google Calendar
- During capture: email is read back in full then spelled out character by character ("I have john.smith@gmail.com — j-o-h-n dot s-m-i-t-h at gmail dot com — is that correct?"); address is read back in full and caller asked "is that right?"
- Reschedule: agent reads back old and new time before updating ("I'll move your Thursday 2pm to Tuesday at 10am — shall I go ahead?")
- Cancellation: explicit intent confirmation before removing ("Just to confirm, you'd like to cancel your Thursday 2pm — is that right?")
- If caller says no during final confirmation: "No problem — what would you like to adjust?" and let them correct
- After successful action: confirm + "Is there anything else I can help you with?"
- Unclear/no response at any confirmation step: retry up to 2 times, then transfer to team

### Availability Window (Per-Client Config)
- Business hours, working days, slot duration, buffer between appointments, minimum lead time, and timezone are all configured per client — stored as columns on the existing clients table
- Google Calendar is the sole source of truth for availability — no cross-referencing with a local DB
- If caller tries to book outside business hours or on a day off: agent explains and offers the next available slot ("We're not available on Sundays — the next opening I have is Monday at 10am")
- Google Calendar API errors mid-call: apologize and transfer ("I'm having trouble accessing the calendar right now — let me connect you with someone who can help")

### Claude's Discretion
- Exact schema column names for per-client config fields
- How to parse and validate business hours / working days from DB storage
- Google Calendar API library and OAuth token refresh logic
- Exact Retell tool call structure for calendar operations

</decisions>

<specifics>
## Specific Ideas

- This is for appliance repair businesses — the agent sounds like a knowledgeable repair shop receptionist
- Access notes field captures gate codes, door codes, building access instructions — anything a tech needs to reach the property
- The per-client config pattern is already established in Phase 1 (clients table) — calendar config extends that same record

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-calendar-operations*
*Context gathered: 2026-04-03*
