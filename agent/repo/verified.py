import json
import sqlite3
from datetime import datetime

from shared.sqlite import many, one
from shared.time import parse_utc


def decode(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {**row, "slot": json.loads(row["slot_json"])}


def get(conn: sqlite3.Connection, booking_id: str) -> dict | None:
    return decode(one(conn, "SELECT * FROM verified_state WHERE booking_id = ?", (booking_id,)))


def for_customer(conn: sqlite3.Connection, customer_id: str) -> list[dict]:
    rows = many(conn, "SELECT * FROM verified_state WHERE customer_id = ? ORDER BY observed_utc DESC", (customer_id,))
    return [decode(row) for row in rows]


def by_ref(conn: sqlite3.Connection, customer_id: str, ref: str) -> dict | None:
    row = one(
        conn, "SELECT * FROM verified_state WHERE customer_id = ? AND upper(ref) = upper(?)", (customer_id, ref.strip())
    )
    return decode(row)


def active_for_customer(conn: sqlite3.Connection, customer_id: str, now: datetime) -> list[dict]:
    rows = [row for row in for_customer(conn, customer_id) if row["status"] == "confirmed"]
    upcoming = [row for row in rows if parse_utc(row["slot"]["start_utc"]) > now]
    return sorted(upcoming, key=lambda row: row["slot"]["start_utc"])


def is_fresh(row: dict, now: datetime, ttl_s: float, session_id: str | None) -> bool:
    age = (now - parse_utc(row["observed_utc"])).total_seconds()
    trusted_source = row["source"] in ("webhook", "poll") or row["fetched_in_session"] == session_id
    return age <= ttl_s and trusted_source
