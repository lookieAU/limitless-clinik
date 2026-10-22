import json
import sqlite3
from datetime import datetime

from shared.ids import new_id
from shared.sqlite import many
from shared.time import to_iso_z


def create_notice(
    conn: sqlite3.Connection,
    user_id: str,
    booking_id: str,
    template_key: str,
    params: dict,
    now: datetime,
    event_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO pending_notices (id, user_id, event_id, booking_id, template_key, params_json, created_utc) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id("ntc"), user_id, event_id, booking_id, template_key, json.dumps(params), to_iso_z(now)),
    )


def undelivered(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = many(
        conn, "SELECT * FROM pending_notices WHERE user_id = ? AND delivered_utc IS NULL ORDER BY rowid", (user_id,)
    )
    return [{**row, "params": json.loads(row["params_json"])} for row in rows]


def mark_delivered(conn: sqlite3.Connection, notice_ids: list[str], now: datetime) -> None:
    conn.executemany(
        "UPDATE pending_notices SET delivered_utc = ? WHERE id = ?", [(to_iso_z(now), notice_id) for notice_id in notice_ids]
    )
