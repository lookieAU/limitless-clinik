CREATE TABLE clinics (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tz TEXT NOT NULL,
    policy_json TEXT NOT NULL
);

CREATE TABLE doctors (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    name TEXT NOT NULL
);

CREATE TABLE customers (
    id TEXT PRIMARY KEY,
    external_ref TEXT NOT NULL
);

CREATE TABLE slots (
    id TEXT PRIMARY KEY,
    doctor_id TEXT NOT NULL REFERENCES doctors(id),
    start_utc TEXT NOT NULL,
    end_utc TEXT NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 1,
    booked_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX slots_doctor_start ON slots (doctor_id, start_utc);

CREATE TABLE bookings (
    id TEXT PRIMARY KEY,
    ref TEXT NOT NULL UNIQUE,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    customer_id TEXT NOT NULL REFERENCES customers(id),
    slot_id TEXT NOT NULL REFERENCES slots(id),
    status TEXT NOT NULL,
    cancelled_by TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_utc TEXT NOT NULL,
    updated_utc TEXT NOT NULL
);
CREATE INDEX bookings_customer ON bookings (clinic_id, customer_id);

CREATE TABLE idempotency_keys (
    key TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    booking_id TEXT,
    status_code INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    created_utc TEXT NOT NULL
);

CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    clinic_id TEXT NOT NULL,
    type TEXT NOT NULL,
    booking_id TEXT NOT NULL,
    origin TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_utc TEXT NOT NULL,
    delivered_utc TEXT,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE faults (
    endpoint TEXT PRIMARY KEY,
    mode TEXT NOT NULL
);
