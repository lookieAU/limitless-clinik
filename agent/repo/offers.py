import json
import sqlite3
from datetime import datetime

from shared.ids import new_id
from shared.sqlite import many
from shared.time import to_iso_z
from shared.types import Slot


def replace_offers(
    conn: sqlite3.Connection,
    session_id: str,
    slots: list[Slot],
    action: str,
    target_booking_id: str | None,
    now: datetime,
) -> list[dict]:
    conn.execute("UPDATE pending_offers SET status = 'superseded' WHERE session_id = ? AND status = 'open'", (session_id,))
    for slot in slots:
        conn.execute(
            "INSERT INTO pending_offers (id, session_id, clinic_id, slot_id, slot_json, action, target_booking_id, offered_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("ofr"),
                session_id,
                slot.clinic_id,
                slot.id,
                slot.model_dump_json(),
                action,
                target_booking_id,
                to_iso_z(now),
            ),
        )
    return open_offers(conn, session_id)


def open_offers(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = many(conn, "SELECT * FROM pending_offers WHERE session_id = ? AND status = 'open' ORDER BY rowid", (session_id,))
    return [{**row, "slot": json.loads(row["slot_json"])} for row in rows]


def set_status(conn: sqlite3.Connection, offer_id: str, status: str) -> None:
    conn.execute("UPDATE pending_offers SET status = ? WHERE id = ?", (status, offer_id))


def close_open(conn: sqlite3.Connection, session_id: str, status: str) -> None:
    conn.execute("UPDATE pending_offers SET status = ? WHERE session_id = ? AND status = 'open'", (status, session_id))
