import sqlite3

from agent_install_monitor import db


def _record(db_path, session_id="sess-1", name="discord.js", agent="hermes"):
    db.record_event(
        session_id=session_id,
        category="package_manager",
        manager="npm",
        action="install",
        name=name,
        version=None,
        command=f"npm install {name}",
        cwd="/home/user/project",
        exit_code=0,
        success=True,
        tool_call_id="tc-1",
        agent=agent,
        db_path=db_path,
    )


def test_record_event_creates_session_and_event(tmp_path):
    db_path = tmp_path / "monitor.db"
    _record(db_path)

    sessions = db.list_sessions(db_path=db_path)
    assert len(sessions) == 1
    assert sessions[0].session_id == "sess-1"
    assert sessions[0].event_count == 1

    events = db.events_for_session("sess-1", db_path=db_path)
    assert len(events) == 1
    assert events[0].name == "discord.js"
    assert events[0].success is True


def test_repeated_events_increment_session_count(tmp_path):
    db_path = tmp_path / "monitor.db"
    _record(db_path, name="discord.js")
    _record(db_path, name="typescript")

    session = db.get_session("sess-1", db_path=db_path)
    assert session is not None
    assert session.event_count == 2

    events = db.events_for_session("sess-1", db_path=db_path)
    assert [e.name for e in events] == ["discord.js", "typescript"]


def test_latest_session_id(tmp_path):
    db_path = tmp_path / "monitor.db"
    _record(db_path, session_id="sess-1")
    _record(db_path, session_id="sess-2")

    assert db.latest_session_id(db_path=db_path) == "sess-2"


def test_get_session_missing_returns_none(tmp_path):
    db_path = tmp_path / "monitor.db"
    assert db.get_session("nope", db_path=db_path) is None


def test_all_events_across_sessions(tmp_path):
    db_path = tmp_path / "monitor.db"
    _record(db_path, session_id="sess-1")
    _record(db_path, session_id="sess-2")

    events = db.all_events(db_path=db_path)
    assert len(events) == 2


def test_failed_command_recorded_as_unsuccessful(tmp_path):
    db_path = tmp_path / "monitor.db"
    db.record_event(
        session_id="sess-1", category="package_manager", manager="pip",
        action="install", name="nonexistent-pkg", version=None,
        command="pip install nonexistent-pkg", cwd=None, exit_code=1,
        success=False, db_path=db_path,
    )
    events = db.events_for_session("sess-1", db_path=db_path)
    assert events[0].success is False
    assert events[0].exit_code == 1


def test_get_home_dir_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert db.get_home_dir() == tmp_path.resolve()


def test_session_records_agent(tmp_path):
    db_path = tmp_path / "monitor.db"
    _record(db_path, agent="hermes")

    session = db.get_session("sess-1", db_path=db_path)
    assert session is not None
    assert session.agent == "hermes"


def test_default_agent_is_hermes_when_unspecified(tmp_path):
    db_path = tmp_path / "monitor.db"
    db.record_event(
        session_id="sess-1", category="package_manager", manager="pip",
        action="install", name="openai", version=None,
        command="pip install openai", cwd=None, exit_code=0,
        success=True, db_path=db_path,
    )
    assert db.get_session("sess-1", db_path=db_path).agent == "hermes"


def test_second_agent_can_write_alongside_first(tmp_path):
    db_path = tmp_path / "monitor.db"
    _record(db_path, session_id="sess-hermes", agent="hermes")
    _record(db_path, session_id="sess-other", agent="some-other-agent")

    sessions = {s.session_id: s.agent for s in db.list_sessions(db_path=db_path)}
    assert sessions == {"sess-hermes": "hermes", "sess-other": "some-other-agent"}


def test_migration_adds_agent_column_without_losing_existing_data(tmp_path):
    # Build a database on the pre-agent-column schema (as if written by an
    # older version of this package), then confirm connecting through the
    # current db module migrates it in place -- old rows survive and get
    # backfilled with agent='hermes' rather than being dropped/recreated.
    db_path = tmp_path / "monitor.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE sessions (
            session_id   TEXT PRIMARY KEY,
            started_at   TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            event_count  INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE events (
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
        """
    )
    conn.execute(
        "INSERT INTO sessions VALUES ('legacy-sess', '2020-01-01T00:00:00+00:00', "
        "'2020-01-01T00:00:00+00:00', 1)"
    )
    conn.execute(
        "INSERT INTO events (session_id, timestamp, category, manager, action, name, "
        "version, command, cwd, exit_code, success, tool_call_id) VALUES "
        "('legacy-sess', '2020-01-01T00:00:00+00:00', 'package_manager', 'pip', "
        "'install', 'old-pkg', NULL, 'pip install old-pkg', NULL, 0, 1, NULL)"
    )
    conn.commit()
    conn.close()

    session = db.get_session("legacy-sess", db_path=db_path)
    assert session is not None
    assert session.agent == "hermes"  # backfilled default for pre-migration rows

    events = db.events_for_session("legacy-sess", db_path=db_path)
    assert len(events) == 1
    assert events[0].name == "old-pkg"  # nothing lost in the migration

    # Migration is idempotent: reconnecting doesn't error or re-apply.
    db.record_event(
        session_id="legacy-sess", category="package_manager", manager="pip",
        action="install", name="new-pkg", version=None,
        command="pip install new-pkg", cwd=None, exit_code=0,
        success=True, db_path=db_path,
    )
    assert db.get_session("legacy-sess", db_path=db_path).event_count == 2
