import json
import sqlite3
from datetime import datetime

from shared.sqlite import many
from shared.time import to_iso_z


def log_event(
    conn: sqlite3.Connection,
    now: datetime,
    event_type: str,
    payload: dict,
    user_id: str | None = None,
    session_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO events (type, user_id, session_id, payload_json, created_utc) VALUES (?, ?, ?, ?, ?)",
        (event_type, user_id, session_id, json.dumps(payload, default=str), to_iso_z(now)),
    )


def recent_events(conn: sqlite3.Connection, user_id: str, limit: int = 40) -> list[dict]:
    rows = many(
        conn, "SELECT id, type, payload_json, created_utc FROM events WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
    )
    return [{**row, "payload": json.loads(row["payload_json"])} for row in rows]


def events_of_type(conn: sqlite3.Connection, event_type: str, user_id: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM events WHERE type = ?", [event_type]
    if user_id:
        sql += " AND user_id = ?"
        params.append(user_id)
    rows = many(conn, sql + " ORDER BY id", tuple(params))
    return [{**row, "payload": json.loads(row["payload_json"])} for row in rows]
