import json
import sqlite3
from datetime import datetime

from shared.ids import new_id
from shared.sqlite import many, one
from shared.time import to_iso_z


def add_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    text: str,
    lang: str,
    now: datetime,
    client_msg_id: str | None = None,
) -> str:
    message_id = new_id("msg")
    conn.execute(
        "INSERT INTO messages (id, session_id, role, text, lang, client_msg_id, created_utc) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (message_id, session_id, role, text, lang, client_msg_id, to_iso_z(now)),
    )
    return message_id


def prior_result(conn: sqlite3.Connection, session_id: str, client_msg_id: str | None) -> dict | None:
    if not client_msg_id:
        return None
    row = one(
        conn,
        "SELECT result_json FROM messages WHERE session_id = ? AND client_msg_id = ? AND result_json IS NOT NULL",
        (session_id, client_msg_id),
    )
    return json.loads(row["result_json"]) if row else None


def store_result(conn: sqlite3.Connection, message_id: str, result: dict) -> None:
    conn.execute("UPDATE messages SET result_json = ? WHERE id = ?", (json.dumps(result), message_id))


def recent(conn: sqlite3.Connection, session_id: str, limit: int = 8) -> list[dict]:
    rows = many(
        conn,
        "SELECT role, text FROM messages WHERE session_id = ? ORDER BY rowid DESC LIMIT ?",
        (session_id, limit),
    )
    return list(reversed(rows))


def transcript(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    return many(
        conn, "SELECT id, role, text, lang, result_json, created_utc FROM messages WHERE session_id = ? ORDER BY rowid", (session_id,)
    )
