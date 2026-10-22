import sqlite3

MODES = ("none", "timeout_before_commit", "timeout_after_commit", "slow")
ENDPOINTS = ("book", "reschedule", "cancel")
ONE_SHOT = ("timeout_before_commit", "timeout_after_commit")


def set_fault(conn: sqlite3.Connection, endpoint: str, mode: str) -> None:
    if endpoint not in ENDPOINTS or mode not in MODES:
        raise ValueError(f"unknown fault {endpoint}:{mode}")
    conn.execute(
        "INSERT INTO faults (endpoint, mode) VALUES (?, ?) ON CONFLICT(endpoint) DO UPDATE SET mode = excluded.mode",
        (endpoint, mode),
    )


def take_fault(conn: sqlite3.Connection, endpoint: str) -> str:
    row = conn.execute("SELECT mode FROM faults WHERE endpoint = ?", (endpoint,)).fetchone()
    mode = row["mode"] if row else "none"
    if mode in ONE_SHOT:
        set_fault(conn, endpoint, "none")
    return mode


def all_faults(conn: sqlite3.Connection) -> dict[str, str]:
    current = {row["endpoint"]: row["mode"] for row in conn.execute("SELECT * FROM faults")}
    return {endpoint: current.get(endpoint, "none") for endpoint in ENDPOINTS}
