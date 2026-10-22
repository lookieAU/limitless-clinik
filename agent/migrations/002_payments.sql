CREATE TABLE payment_intents (
    id TEXT PRIMARY KEY,
    booking_id TEXT,
    user_id TEXT NOT NULL REFERENCES users(id),
    provider TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor >= 0),
    currency TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requires_authorization', 'authorized', 'captured', 'voided', 'refunded', 'failed')),
    idempotency_key TEXT NOT NULL UNIQUE,
    provider_ref TEXT,
    observed_utc TEXT,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);

CREATE TABLE payment_events (
    id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL REFERENCES payment_intents(id),
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_utc TEXT NOT NULL
);
