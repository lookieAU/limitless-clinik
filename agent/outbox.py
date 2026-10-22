import json
import sqlite3
from datetime import datetime

from shared.ids import new_id
from shared.sqlite import many, one
from shared.time import to_iso_z


def begin(
    conn: sqlite3.Connection, user_id: str, action: str, payload: dict, key: str, intent_id: str, now: datetime
) -> dict:
    existing = one(conn, "SELECT * FROM outbox WHERE idempotency_key = ?", (key,))
    if existing:
        return existing
    stamp = to_iso_z(now)
    conn.execute(
        "INSERT INTO outbox (id, user_id, action, payload_json, idempotency_key, intent_id, state, created_utc, updated_utc) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
        (new_id("obx"), user_id, action, json.dumps(payload), key, intent_id, stamp, stamp),
    )
    return one(conn, "SELECT * FROM outbox WHERE idempotency_key = ?", (key,))


def mark(conn: sqlite3.Connection, row_id: str, state: str, now: datetime, result: dict | None = None) -> None:
    conn.execute(
        "UPDATE outbox SET state = ?, result_json = COALESCE(?, result_json), updated_utc = ? WHERE id = ?",
        (state, json.dumps(result) if result is not None else None, to_iso_z(now), row_id),
    )


def unknown_for_user(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    return many(conn, "SELECT * FROM outbox WHERE user_id = ? AND state = 'unknown' ORDER BY rowid", (user_id,))


def for_user(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    return many(conn, "SELECT * FROM outbox WHERE user_id = ? ORDER BY rowid", (user_id,))
