import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta

from clinic.clinics import CLINICS, ClinicConfig
from clinic.repo import ClinicError, booking_json, booking_row
from shared.ids import new_id
from shared.sqlite import one, transaction
from shared.time import parse_utc, to_iso_z


def request_hash(method: str, path: str, body: dict) -> str:
    material = json.dumps({"m": method, "p": path, "b": body}, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()


def run_idempotent(
    conn: sqlite3.Connection,
    key: str,
    req_hash: str,
    now: datetime,
    action: Callable[[], tuple[int, dict]],
) -> tuple[int, dict]:
    with transaction(conn):
        existing = one(conn, "SELECT * FROM idempotency_keys WHERE key = ?", (key,))
        if existing:
            if existing["request_hash"] != req_hash:
                raise ClinicError(409, "idempotency_conflict", "key reused with a different request")
            return existing["status_code"], json.loads(existing["response_json"])
        status, body = action()
        conn.execute(
            "INSERT INTO idempotency_keys (key, request_hash, booking_id, status_code, response_json, created_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key, req_hash, body.get("booking_id"), status, json.dumps(body), to_iso_z(now)),
        )
        return status, body


def emit(conn: sqlite3.Connection, clinic: ClinicConfig, kind: str, booking_id: str, origin: str, now: datetime) -> dict:
    payload = {
        "event_id": new_id("evt"),
        "clinic_id": clinic.id,
        "type": clinic.event_names[kind],
        "occurred_utc": to_iso_z(now),
        "booking": booking_json(conn, booking_row(conn, clinic.id, booking_id)),
    }
    conn.execute(
        "INSERT INTO events (id, clinic_id, type, booking_id, origin, payload_json, occurred_utc) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (payload["event_id"], clinic.id, payload["type"], booking_id, origin, json.dumps(payload), payload["occurred_utc"]),
    )
    return payload


def take_capacity(conn: sqlite3.Connection, clinic_id: str, slot_id: str) -> None:
    owner = one(
        conn, "SELECT d.clinic_id FROM slots s JOIN doctors d ON d.id = s.doctor_id WHERE s.id = ?", (slot_id,)
    )
    if owner is None or owner["clinic_id"] != clinic_id:
        raise ClinicError(404, "slot_not_found")
    cursor = conn.execute(
        "UPDATE slots SET booked_count = booked_count + 1, version = version + 1 "
        "WHERE id = ? AND status = 'open' AND booked_count < capacity",
        (slot_id,),
    )
    if cursor.rowcount == 0:
        raise ClinicError(409, "slot_unavailable", "that slot is no longer available")


def release_capacity(conn: sqlite3.Connection, slot_id: str) -> None:
    conn.execute(
        "UPDATE slots SET booked_count = MAX(booked_count - 1, 0), version = version + 1 WHERE id = ?", (slot_id,)
    )


def create_booking(conn: sqlite3.Connection, clinic: ClinicConfig, customer_id: str, slot_id: str, now: datetime) -> dict:
    if one(conn, "SELECT id FROM customers WHERE id = ?", (customer_id,)) is None:
        raise ClinicError(404, "customer_not_found")
    take_capacity(conn, clinic.id, slot_id)
    count = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    per_clinic = conn.execute("SELECT COUNT(*) FROM bookings WHERE clinic_id = ?", (clinic.id,)).fetchone()[0]
    booking_id = f"bk_{count + 1:04d}"
    stamp = to_iso_z(now)
    conn.execute(
        "INSERT INTO bookings (id, ref, clinic_id, customer_id, slot_id, status, version, created_utc, updated_utc) "
        "VALUES (?, ?, ?, ?, ?, 'confirmed', 1, ?, ?)",
        (booking_id, f"{clinic.ref_prefix}-{1001 + per_clinic}", clinic.id, customer_id, slot_id, stamp, stamp),
    )
    emit(conn, clinic, "created", booking_id, "customer", now)
    return booking_json(conn, booking_row(conn, clinic.id, booking_id))


def move_booking(
    conn: sqlite3.Connection,
    clinic: ClinicConfig,
    booking_id: str,
    slot_id: str,
    expected_version: int | None,
    now: datetime,
    origin: str,
) -> tuple[dict, dict]:
    row = booking_row(conn, clinic.id, booking_id)
    if row["status"] != "confirmed":
        raise ClinicError(409, "booking_not_active")
    if expected_version is not None and row["version"] != expected_version:
        raise ClinicError(412, "version_mismatch", f"current version is {row['version']}")
    if slot_id != row["slot_id"]:
        take_capacity(conn, clinic.id, slot_id)
        release_capacity(conn, row["slot_id"])
    conn.execute(
        "UPDATE bookings SET slot_id = ?, version = version + 1, updated_utc = ? WHERE id = ?",
        (slot_id, to_iso_z(now), booking_id),
    )
    event = emit(conn, clinic, "rescheduled", booking_id, origin, now)
    return booking_json(conn, booking_row(conn, clinic.id, booking_id)), event


def cancel_booking(
    conn: sqlite3.Connection, clinic: ClinicConfig, booking_id: str, now: datetime, origin: str
) -> tuple[dict, dict | None]:
    row = booking_row(conn, clinic.id, booking_id)
    if row["status"] == "cancelled":
        return booking_json(conn, row), None
    if origin == "customer" and clinic.cancel_cutoff_hours:
        start = parse_utc(booking_json(conn, row)["slot"]["start_utc"])
        if start - now < timedelta(hours=clinic.cancel_cutoff_hours):
            raise ClinicError(409, "cancel_cutoff", f"cancellations need {clinic.cancel_cutoff_hours}h notice")
    conn.execute(
        "UPDATE bookings SET status = 'cancelled', cancelled_by = ?, version = version + 1, updated_utc = ? WHERE id = ?",
        (origin, to_iso_z(now), booking_id),
    )
    release_capacity(conn, row["slot_id"])
    event = emit(conn, clinic, "cancelled", booking_id, origin, now)
    return booking_json(conn, booking_row(conn, clinic.id, booking_id)), event


def cancel_slot(conn: sqlite3.Connection, slot_id: str, now: datetime) -> list[dict]:
    owner = one(conn, "SELECT d.clinic_id FROM slots s JOIN doctors d ON d.id = s.doctor_id WHERE s.id = ?", (slot_id,))
    if owner is None:
        raise ClinicError(404, "slot_not_found")
    clinic = CLINICS[owner["clinic_id"]]
    events = []
    with transaction(conn):
        conn.execute("UPDATE slots SET status = 'cancelled', version = version + 1 WHERE id = ?", (slot_id,))
        active = conn.execute(
            "SELECT id FROM bookings WHERE slot_id = ? AND status = 'confirmed' ORDER BY id", (slot_id,)
        ).fetchall()
        for booking in active:
            _, event = cancel_booking(conn, clinic, booking["id"], now, "clinic")
            events.append(event)
    return events


def fill_slot(conn: sqlite3.Connection, slot_id: str) -> None:
    cursor = conn.execute("UPDATE slots SET booked_count = capacity, version = version + 1 WHERE id = ?", (slot_id,))
    if cursor.rowcount == 0:
        raise ClinicError(404, "slot_not_found")
