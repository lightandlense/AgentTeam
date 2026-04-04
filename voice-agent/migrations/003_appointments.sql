-- appointments table: durable record of every booked appointment
-- Primary lookup key is caller_phone — avoids name-collision ambiguity
-- status: 'active' | 'cancelled'
CREATE TABLE IF NOT EXISTS appointments (
    id           SERIAL PRIMARY KEY,
    client_id    TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    event_id     TEXT NOT NULL,
    caller_phone TEXT NOT NULL,
    caller_name  TEXT NOT NULL,
    caller_email TEXT NOT NULL DEFAULT '',
    slot_dt      TIMESTAMPTZ NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS appointments_phone_idx
    ON appointments (client_id, caller_phone);

CREATE INDEX IF NOT EXISTS appointments_event_id_idx
    ON appointments (event_id);
