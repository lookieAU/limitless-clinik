CREATE TABLE users (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    tz TEXT NOT NULL,
    preferred_lang TEXT NOT NULL,
    ics_token TEXT NOT NULL UNIQUE,
    created_utc TEXT NOT NULL
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    started_utc TEXT NOT NULL,
    last_seen_utc TEXT NOT NULL,
    synced_utc TEXT,
    state TEXT NOT NULL DEFAULT 'idle',
    state_json TEXT NOT NULL DEFAULT '{}',
    lang TEXT NOT NULL DEFAULT 'en'
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    lang TEXT NOT NULL,
    client_msg_id TEXT,
    result_json TEXT,
    created_utc TEXT NOT NULL
);
CREATE UNIQUE INDEX messages_client ON messages (session_id, client_msg_id) WHERE client_msg_id IS NOT NULL;

CREATE TABLE claims (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    session_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    subject TEXT NOT NULL,
    value TEXT NOT NULL,
    polarity TEXT NOT NULL CHECK (polarity IN ('positive', 'negative')),
    raw_text TEXT NOT NULL,
    lang TEXT NOT NULL,
    booking_hint TEXT,
    source TEXT NOT NULL DEFAULT 'customer_message',
    status TEXT NOT NULL DEFAULT 'active',
    superseded_by TEXT,
    overridden_by_event TEXT,
    created_utc TEXT NOT NULL
);
CREATE INDEX claims_user ON claims (user_id, status);

CREATE TABLE verified_state (
    booking_id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    ref TEXT NOT NULL,
    status TEXT NOT NULL,
    slot_json TEXT NOT NULL,
    version INTEGER NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('api', 'webhook', 'poll')),
    observed_utc TEXT NOT NULL,
    fetched_in_session TEXT
);
CREATE INDEX verified_customer ON verified_state (customer_id);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    user_id TEXT,
    session_id TEXT,
    payload_json TEXT NOT NULL,
    created_utc TEXT NOT NULL
);
CREATE INDEX events_user ON events (user_id, id);

CREATE TABLE processed_events (
    event_id TEXT PRIMARY KEY,
    received_utc TEXT NOT NULL
);

CREATE TABLE poll_cursors (
    clinic_id TEXT PRIMARY KEY,
    last_seq INTEGER NOT NULL
);

CREATE TABLE outbox (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    intent_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'in_flight', 'succeeded', 'failed', 'unknown')),
    result_json TEXT,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

CREATE TABLE pending_offers (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    clinic_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    slot_json TEXT NOT NULL,
    action TEXT NOT NULL,
    target_booking_id TEXT,
    offered_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE pending_notices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_id TEXT,
    booking_id TEXT NOT NULL,
    template_key TEXT NOT NULL,
    params_json TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    delivered_utc TEXT
);

CREATE TABLE memory_summaries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    day_local TEXT NOT NULL,
    structured_json TEXT NOT NULL,
    prose TEXT NOT NULL,
    lang TEXT NOT NULL,
    validated INTEGER NOT NULL,
    errors_json TEXT NOT NULL DEFAULT '[]',
    created_utc TEXT NOT NULL
);

CREATE TABLE claim_embeddings (
    claim_id TEXT PRIMARY KEY REFERENCES claims(id),
    model TEXT NOT NULL,
    vector BLOB NOT NULL
);
