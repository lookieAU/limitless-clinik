import json
import sqlite3
from datetime import datetime

from shared.ids import new_id
from shared.sqlite import one
from shared.time import to_iso_z


def create_session(conn: sqlite3.Connection, user: dict, now: datetime) -> dict:
    session_id = new_id("ses")
    stamp = to_iso_z(now)
    conn.execute(
        "INSERT INTO sessions (id, user_id, started_utc, last_seen_utc, lang) VALUES (?, ?, ?, ?, ?)",
        (session_id, user["id"], stamp, stamp, user["preferred_lang"]),
    )
    return get_session(conn, session_id)


def get_session(conn: sqlite3.Connection, session_id: str) -> dict | None:
    return one(conn, "SELECT * FROM sessions WHERE id = ?", (session_id,))


def touch(conn: sqlite3.Connection, session_id: str, now: datetime, lang: str) -> None:
    conn.execute("UPDATE sessions SET last_seen_utc = ?, lang = ? WHERE id = ?", (to_iso_z(now), lang, session_id))


def mark_synced(conn: sqlite3.Connection, session_id: str, now: datetime) -> None:
    conn.execute("UPDATE sessions SET synced_utc = ? WHERE id = ?", (to_iso_z(now), session_id))


def set_state(conn: sqlite3.Connection, session_id: str, state: str, data: dict | None = None) -> None:
    conn.execute(
        "UPDATE sessions SET state = ?, state_json = ? WHERE id = ?", (state, json.dumps(data or {}), session_id)
    )


def state_data(session: dict) -> dict:
    return json.loads(session.get("state_json") or "{}")
