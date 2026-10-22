import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def migrate(conn: sqlite3.Connection, directory: Path) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
    applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
    ran = []
    for path in sorted(directory.glob("*.sql")):
        if path.name in applied:
            continue
        script = path.read_text(encoding="utf-8")
        conn.executescript(
            f"BEGIN;\n{script}\nINSERT INTO schema_migrations (name) VALUES ('{path.name}');\nCOMMIT;"
        )
        ran.append(path.name)
    return ran


def one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def many(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params)]
