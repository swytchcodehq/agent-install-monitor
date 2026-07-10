"""SQLite persistence for Agent Install Monitor.

Plain functions over a single connection-per-call -- no ORM, no connection
pool. ``_SCHEMA`` always reflects the current structure (for fresh installs);
``_MIGRATIONS`` carries the incremental ``ALTER TABLE`` steps needed to bring
an existing database from an older version up to current, gated on SQLite's
built-in ``PRAGMA user_version``. Add a feature that needs a new column?
Add it to ``_SCHEMA``, bump ``_SCHEMA_VERSION``, and append the matching
``ALTER TABLE`` to ``_MIGRATIONS``.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    agent        TEXT NOT NULL DEFAULT 'hermes',
    started_at   TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    event_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    category     TEXT NOT NULL,
    manager      TEXT,
    action       TEXT,
    name         TEXT,
    version      TEXT,
    command      TEXT NOT NULL,
    cwd          TEXT,
    exit_code    INTEGER,
    success      INTEGER NOT NULL,
    tool_call_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
"""

# Bump whenever _SCHEMA changes, and append the matching ALTER TABLE(s) below
# keyed on the version that introduces them. Applied in order to databases
# created before that version; fresh databases are created directly from
# _SCHEMA and stamped at the current version, so they never run these.
_SCHEMA_VERSION = 2
_MIGRATIONS: List[Tuple[int, str]] = [
    (2, "ALTER TABLE sessions ADD COLUMN agent TEXT NOT NULL DEFAULT 'hermes'"),
]


def _init_schema(conn: sqlite3.Connection) -> None:
    preexisting = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'"
    ).fetchone() is not None
    conn.executescript(_SCHEMA)
    if preexisting:
        _run_migrations(conn)
    else:
        conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def _run_migrations(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for target_version, statement in _MIGRATIONS:
        if version < target_version:
            conn.execute(statement)
            version = target_version
    conn.execute(f"PRAGMA user_version = {version}")


def get_home_dir() -> Path:
    """``$HERMES_HOME`` if set, else ``~/.hermes``.

    Deliberately reads the env var directly rather than importing
    ``hermes_constants`` -- this package has no runtime dependency on
    hermes-agent, so the ``agent-monitor`` CLI works even in an environment
    where hermes-agent itself isn't importable.
    """
    val = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(val).expanduser().resolve() if val else (Path.home() / ".hermes").resolve()


def get_db_path() -> Path:
    return get_home_dir() / "agent-monitor" / "monitor.db"


@contextmanager
def _connect(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        _init_schema(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_event(
    *,
    session_id: str,
    category: str,
    manager: Optional[str],
    action: Optional[str],
    name: Optional[str],
    version: Optional[str],
    command: str,
    cwd: Optional[str],
    exit_code: Optional[int],
    success: bool,
    tool_call_id: Optional[str] = None,
    agent: str = "hermes",
    db_path: Optional[Path] = None,
) -> None:
    """Record one detected event, creating/touching its session.

    ``agent`` identifies which agent's plugin adapter produced this event
    (e.g. ``"hermes"``) -- it's only set on first insert of a session, never
    changed on later events for the same session_id.
    """
    ts = _now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sessions (session_id, agent, started_at, last_seen_at, event_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(session_id) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                event_count = event_count + 1
            """,
            (session_id, agent, ts, ts),
        )
        conn.execute(
            """
            INSERT INTO events (
                session_id, timestamp, category, manager, action, name, version,
                command, cwd, exit_code, success, tool_call_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, ts, category, manager, action, name, version,
                command, cwd, exit_code, int(bool(success)), tool_call_id,
            ),
        )


@dataclass
class SessionSummary:
    session_id: str
    agent: str
    started_at: str
    last_seen_at: str
    event_count: int


@dataclass
class Event:
    id: int
    session_id: str
    timestamp: str
    category: str
    manager: Optional[str]
    action: Optional[str]
    name: Optional[str]
    version: Optional[str]
    command: str
    cwd: Optional[str]
    exit_code: Optional[int]
    success: bool
    tool_call_id: Optional[str]


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"], session_id=row["session_id"], timestamp=row["timestamp"],
        category=row["category"], manager=row["manager"], action=row["action"],
        name=row["name"], version=row["version"], command=row["command"],
        cwd=row["cwd"], exit_code=row["exit_code"], success=bool(row["success"]),
        tool_call_id=row["tool_call_id"],
    )


def _row_to_session(row: sqlite3.Row) -> SessionSummary:
    return SessionSummary(
        row["session_id"], row["agent"], row["started_at"], row["last_seen_at"], row["event_count"],
    )


def list_sessions(db_path: Optional[Path] = None) -> List[SessionSummary]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT session_id, agent, started_at, last_seen_at, event_count "
            "FROM sessions ORDER BY started_at DESC"
        ).fetchall()
    return [_row_to_session(row) for row in rows]


def latest_session_id(db_path: Optional[Path] = None) -> Optional[str]:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT session_id FROM sessions ORDER BY last_seen_at DESC LIMIT 1"
        ).fetchone()
    return row["session_id"] if row else None


def get_session(session_id: str, db_path: Optional[Path] = None) -> Optional[SessionSummary]:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT session_id, agent, started_at, last_seen_at, event_count "
            "FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return _row_to_session(row) if row is not None else None


def events_for_session(session_id: str, db_path: Optional[Path] = None) -> List[Event]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def all_events(db_path: Optional[Path] = None) -> List[Event]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY timestamp ASC").fetchall()
    return [_row_to_event(row) for row in rows]
