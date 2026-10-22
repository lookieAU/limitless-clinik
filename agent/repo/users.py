import secrets
import sqlite3
from datetime import datetime

from shared.sqlite import many, one
from shared.time import to_iso_z

SEED_USERS = (
    ("u_asha", "c_asha", "Asha Kulkarni", "Asia/Kolkata", "en"),
    ("u_ravi", "c_ravi", "Ravi Sharma", "Asia/Kolkata", "hi"),
    ("u_mei", "c_mei", "Mei Tan", "Asia/Singapore", "en"),
)


def seed_users(conn: sqlite3.Connection, now: datetime) -> None:
    for user_id, customer_id, name, tz, lang in SEED_USERS:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, customer_id, display_name, tz, preferred_lang, ics_token, created_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, customer_id, name, tz, lang, secrets.token_urlsafe(18), to_iso_z(now)),
        )


def get_user(conn: sqlite3.Connection, user_id: str) -> dict | None:
    return one(conn, "SELECT * FROM users WHERE id = ?", (user_id,))


def by_customer(conn: sqlite3.Connection, customer_id: str) -> dict | None:
    return one(conn, "SELECT * FROM users WHERE customer_id = ?", (customer_id,))


def by_ics_token(conn: sqlite3.Connection, token: str) -> dict | None:
    return one(conn, "SELECT * FROM users WHERE ics_token = ?", (token,))


def list_users(conn: sqlite3.Connection) -> list[dict]:
    return many(conn, "SELECT * FROM users ORDER BY id")
