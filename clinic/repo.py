import sqlite3

from clinic.clinics import CLINICS
from shared.sqlite import many, one


class ClinicError(Exception):
    def __init__(self, status: int, code: str, detail: str = ""):
        super().__init__(code)
        self.status = status
        self.code = code
        self.detail = detail

    def body(self) -> dict:
        return {"error": self.code, "detail": self.detail}


def slot_json(conn: sqlite3.Connection, slot_id: str) -> dict:
    row = one(
        conn,
        "SELECT s.*, d.name AS doctor_name, d.clinic_id FROM slots s JOIN doctors d ON d.id = s.doctor_id WHERE s.id = ?",
        (slot_id,),
    )
    if row is None:
        raise ClinicError(404, "slot_not_found")
    return {
        "id": row["id"],
        "clinic_id": row["clinic_id"],
        "doctor_id": row["doctor_id"],
        "doctor_name": row["doctor_name"],
        "start_utc": row["start_utc"],
        "end_utc": row["end_utc"],
        "available": row["status"] == "open" and row["booked_count"] < row["capacity"],
    }


def booking_row(conn: sqlite3.Connection, clinic_id: str, booking_id: str) -> dict:
    row = one(conn, "SELECT * FROM bookings WHERE id = ? AND clinic_id = ?", (booking_id, clinic_id))
    if row is None:
        raise ClinicError(404, "booking_not_found")
    return row


def booking_json(conn: sqlite3.Connection, row: dict) -> dict:
    clinic = CLINICS[row["clinic_id"]]
    return {
        "booking_id": row["id"],
        "ref": row["ref"],
        "clinic_id": row["clinic_id"],
        "customer_id": row["customer_id"],
        "status": clinic.raw_status(row["status"], row["cancelled_by"]),
        "version": row["version"],
        "slot": slot_json(conn, row["slot_id"]),
        "updated_utc": row["updated_utc"],
    }


def bookings_for_customer(conn: sqlite3.Connection, clinic_id: str, customer_id: str) -> list[dict]:
    rows = many(
        conn,
        "SELECT * FROM bookings WHERE clinic_id = ? AND customer_id = ? ORDER BY created_utc, id",
        (clinic_id, customer_id),
    )
    return [booking_json(conn, row) for row in rows]


def booking_for_key(conn: sqlite3.Connection, clinic_id: str, key: str) -> list[dict]:
    hit = one(conn, "SELECT booking_id FROM idempotency_keys WHERE key = ?", (key,))
    if hit is None or hit["booking_id"] is None:
        return []
    row = one(conn, "SELECT * FROM bookings WHERE id = ? AND clinic_id = ?", (hit["booking_id"], clinic_id))
    return [booking_json(conn, row)] if row else []


def list_slots(
    conn: sqlite3.Connection,
    clinic_id: str,
    doctor_id: str | None,
    start: str,
    end: str,
    available_only: bool,
) -> list[dict]:
    sql = (
        "SELECT s.id FROM slots s JOIN doctors d ON d.id = s.doctor_id "
        "WHERE d.clinic_id = ? AND s.start_utc >= ? AND s.start_utc < ?"
    )
    params: list = [clinic_id, start, end]
    if doctor_id:
        sql += " AND s.doctor_id = ?"
        params.append(doctor_id)
    if available_only:
        sql += " AND s.status = 'open' AND s.booked_count < s.capacity"
    sql += " ORDER BY s.start_utc, s.doctor_id"
    return [slot_json(conn, row["id"]) for row in many(conn, sql, tuple(params))]


def doctors(conn: sqlite3.Connection, clinic_id: str) -> list[dict]:
    return many(conn, "SELECT id, name FROM doctors WHERE clinic_id = ? ORDER BY id", (clinic_id,))


def events_since(conn: sqlite3.Connection, clinic_id: str, since: int) -> tuple[list[dict], int]:
    rows = many(
        conn, "SELECT seq, payload_json FROM events WHERE clinic_id = ? AND seq > ? ORDER BY seq", (clinic_id, since)
    )
    cursor = rows[-1]["seq"] if rows else since
    return rows, cursor
