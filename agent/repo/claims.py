import sqlite3
from datetime import datetime

from shared.ids import new_id
from shared.sqlite import many, one
from shared.time import to_iso_z

LIVE = ("active", "clarified")
SELECT = "SELECT rowid AS seq, * FROM claims"


def insert_claim(
    conn: sqlite3.Connection,
    user_id: str,
    session_id: str,
    message_id: str,
    draft: dict,
    lang: str,
    now: datetime,
) -> dict:
    claim_id = new_id("clm")
    conn.execute(
        "INSERT INTO claims (id, user_id, session_id, message_id, kind, subject, value, polarity, raw_text, lang, "
        "booking_hint, created_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            claim_id,
            user_id,
            session_id,
            message_id,
            draft["kind"],
            draft["subject"],
            draft["value"],
            draft["polarity"],
            draft["raw_span"],
            lang,
            draft.get("booking_hint"),
            to_iso_z(now),
        ),
    )
    return get(conn, claim_id)


def get(conn: sqlite3.Connection, claim_id: str) -> dict | None:
    return one(conn, f"{SELECT} WHERE id = ?", (claim_id,))


def live_for_session(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    return many(conn, f"{SELECT} WHERE session_id = ? AND status IN {LIVE} ORDER BY rowid", (session_id,))


def live_for_user(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    return many(conn, f"{SELECT} WHERE user_id = ? AND status IN {LIVE} ORDER BY rowid", (user_id,))


def all_for_user(conn: sqlite3.Connection, user_id: str, limit: int = 60) -> list[dict]:
    return many(conn, f"{SELECT} WHERE user_id = ? ORDER BY rowid DESC LIMIT ?", (user_id, limit))


def in_window(conn: sqlite3.Connection, user_id: str, start_utc: str, end_utc: str) -> list[dict]:
    return many(
        conn,
        f"{SELECT} WHERE user_id = ? AND created_utc >= ? AND created_utc < ? ORDER BY rowid",
        (user_id, start_utc, end_utc),
    )


def supersede(conn: sqlite3.Connection, claim_id: str, by: str) -> None:
    conn.execute("UPDATE claims SET status = 'superseded', superseded_by = ? WHERE id = ?", (by, claim_id))


def clarify(conn: sqlite3.Connection, claim_id: str) -> None:
    conn.execute("UPDATE claims SET status = 'clarified' WHERE id = ? AND status = 'active'", (claim_id,))


def hint_booking(conn: sqlite3.Connection, session_id: str, booking_id: str) -> None:
    conn.execute(
        "UPDATE claims SET booking_hint = ? WHERE session_id = ? AND status IN ('active', 'clarified') "
        "AND polarity = 'positive' AND subject IN ('day', 'date', 'time_window', 'week', 'doctor')",
        (booking_id, session_id),
    )


def override_for_booking(conn: sqlite3.Connection, booking_id: str, event_id: str) -> list[str]:
    rows = many(
        conn,
        "SELECT id FROM claims WHERE booking_hint = ? AND polarity = 'positive' AND status IN ('active', 'clarified')",
        (booking_id,),
    )
    conn.execute(
        "UPDATE claims SET status = 'overridden', overridden_by_event = ? WHERE booking_hint = ? "
        "AND polarity = 'positive' AND status IN ('active', 'clarified')",
        (event_id, booking_id),
    )
    return [row["id"] for row in rows]


def overridden_ids(conn: sqlite3.Connection, user_id: str) -> set[str]:
    rows = many(conn, "SELECT id FROM claims WHERE user_id = ? AND status = 'overridden'", (user_id,))
    return {row["id"] for row in rows}
