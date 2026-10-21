"""Storage with simple versioned migrations. SQLite is the default; set OMNI_DATABASE_URL for Postgres.

SQLite is only durable if the file sits on a persistent disk. On hosts with an
ephemeral filesystem (e.g. Render free web services) data is LOST on restart;
see docs/FREE_SERVICES_RESEARCH.md and README before deploying.

Postgres mode (docs/POSTGRES_PLAN.md, Option A): every call site still passes `settings.db_path`; in Postgres
mode that value is a `PgTarget`, and `connect()` returns a wrapper whose `execute()` translates the few SQLite
spellings the code uses (see `translate`). WRITTEN BUT NOT YET VERIFIED against a real Postgres.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New conversation',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE INDEX idx_messages_conv ON messages(conversation_id, id);
        """,
    ),
    (
        2,
        """
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL DEFAULT 'fact' CHECK (kind IN ('fact','preference')),
            content TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT 'Untitled',
            body TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        """,
    ),
    (
        3,
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            due_at TEXT,
            remind_at TEXT,
            done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0,1)),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            tool TEXT NOT NULL,
            outcome TEXT NOT NULL
        );
        """,
    ),
    (
        4,
        """
        CREATE TABLE agent_tasks (
            id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN
                ('queued','running','waiting_approval','succeeded','failed','cancelled','paused','paused_quota')),
            model_calls INTEGER NOT NULL DEFAULT 0,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            summary TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        CREATE TABLE agent_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
            idx INTEGER NOT NULL,
            role TEXT NOT NULL,
            instruction TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed')),
            output TEXT,
            sources TEXT
        );
        CREATE TABLE agent_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES agent_tasks(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            base_content TEXT,
            new_content TEXT NOT NULL,
            diff TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','applied','reverted')),
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        """,
    ),
    (
        5,
        """
        CREATE TABLE skills (
            name TEXT PRIMARY KEY,
            active_version TEXT,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0,1))
        );
        CREATE TABLE skill_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            manifest TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'staged' CHECK (status IN ('staged','active','superseded','rejected')),
            validation TEXT NOT NULL,
            review TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            UNIQUE (name, version)
        );
        """,
    ),
]


def connect(db_path: Path | PgTarget):
    if isinstance(db_path, PgTarget):
        pool = _pool_for(db_path)
        return PgConn(pool.getconn(), pool)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session(db_path: Path | PgTarget) -> Iterator[Any]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def current_version(conn) -> int:
    if isinstance(conn, PgConn):  # init_db creates schema_version first, so it always exists here
        return conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()["v"] or 0
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if row is None:
        return 0
    v = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()["v"]
    return v or 0


def init_db(db_path: Path | PgTarget) -> int:
    """Create/upgrade the schema. Idempotent. Returns the schema version."""
    pg = isinstance(db_path, PgTarget)
    with session(db_path) as conn:
        if pg:
            conn.execute("SELECT pg_advisory_xact_lock(727274)")  # two instances booting at once must not both migrate
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, "
            "applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
        )
        version = current_version(conn)
        for number, sql in (pg_migrations() if pg else MIGRATIONS):
            if number > version:
                conn.executescript(sql)
                conn.execute("INSERT INTO schema_version(version) VALUES (?)", (number,))
                version = number
        return version


def ping(db_path: Path | PgTarget) -> bool:
    try:
        with session(db_path) as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:  # sqlite3.Error, psycopg errors, pool timeouts: any failure means "not reachable"
        return False


def resync_sequences(conn, tables: tuple[str, ...]) -> None:
    """After inserting rows with explicit ids (restore), move Postgres identity counters past them.
    SQLite's AUTOINCREMENT does this by itself, so this is a no-op there."""
    if not isinstance(conn, PgConn):
        return
    for t in tables:
        if t not in AUTOINC_TABLES:
            raise ValueError(t)
        conn.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)")


def get_meta(db_path: Path, key: str) -> str | None:
    with session(db_path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(db_path: Path, key: str, value: str) -> None:
    with session(db_path) as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ---------------------------------------------------------------------------------------------------------
# Postgres support (optional; psycopg is imported lazily so SQLite mode needs nothing extra)
# ---------------------------------------------------------------------------------------------------------
_NOW_SQLITE = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
_NOW_PG = "to_char(timezone('utc', now()), 'YYYY-MM-DD\"T\"HH24:MI:SS.MS\"Z\"')"
# Tables whose INTEGER PRIMARY KEY AUTOINCREMENT id may be read back via `cursor.lastrowid`.
AUTOINC_TABLES = frozenset(re.findall(r"CREATE TABLE (\w+) \(\s*id INTEGER PRIMARY KEY AUTOINCREMENT", "".join(m[1] for m in MIGRATIONS)))
_SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class PgTarget:
    """Stands in for the SQLite file path when OMNI_DATABASE_URL is set. Never prints the password."""

    def __init__(self, url: str, schema: str = ""):
        if schema and not _SCHEMA_NAME.match(schema):
            raise ValueError("OMNI_DATABASE_SCHEMA must be a plain identifier (letters, digits, underscore).")
        self.url, self.schema = url, schema

    def __repr__(self) -> str:  # secrets never leak through logs/reprs
        return "PgTarget(<redacted>)"

    __str__ = __repr__


def is_postgres(target: Any) -> bool:
    return isinstance(target, PgTarget)


def engine_name(target: Any) -> str:
    return "postgres" if is_postgres(target) else "sqlite"


def pg_migrations() -> list[tuple[int, str]]:
    """Postgres DDL generated from the single SQLite DDL source, so the two can never drift apart."""
    out = []
    for number, sql in MIGRATIONS:
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY")
        sql = sql.replace(_NOW_SQLITE, _NOW_PG)
        out.append((number, sql))
    return out


def translate(sql: str, has_params: bool) -> tuple[str, bool]:
    """SQLite -> Postgres for the statements OMNI issues. Returns (sql, wants_returning_id).

    Handles: `?` placeholders, the strftime('now') timestamp, INSERT OR IGNORE, case-insensitive LIKE,
    `rowid` (only used as an ordering tie-break; mapped to ctid), and `lastrowid` (via RETURNING id).
    Anything else is passed through unchanged, so an untranslatable statement fails loudly in Postgres tests.
    """
    s = sql.replace(_NOW_SQLITE, _NOW_PG)
    ignore = bool(re.search(r"\bINSERT OR IGNORE INTO\b", s))
    if ignore:
        s = re.sub(r"\bINSERT OR IGNORE INTO\b", "INSERT INTO", s)
    s = re.sub(r"\bLIKE\b", "ILIKE", s)
    s = re.sub(r"\browid\b", "ctid", s)
    if has_params:
        out, in_quote = [], False
        for ch in s:
            if ch == "'":
                in_quote = not in_quote
            if ch == "%":
                out.append("%%")
            elif ch == "?" and not in_quote:
                out.append("%s")
            else:
                out.append(ch)
        s = "".join(out)
    s = s.rstrip().rstrip(";")
    if ignore:
        s += " ON CONFLICT DO NOTHING"
    m = re.match(r"\s*INSERT INTO (\w+)", s)
    returning = bool(m and m.group(1) in AUTOINC_TABLES and "RETURNING" not in s.upper())
    if returning:
        s += " RETURNING id"
    return s, returning


class _PgResult:
    def __init__(self, cur, lastrowid=None):
        self._cur, self.lastrowid = cur, lastrowid

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class PgConn:
    """Gives a psycopg connection the small slice of the sqlite3 connection API that OMNI's code uses."""

    def __init__(self, raw, pool):
        self._raw, self._pool = raw, pool

    def execute(self, sql: str, params: Any = ()) -> _PgResult:
        text, returning = translate(sql, bool(params))
        cur = self._raw.cursor()
        cur.execute(text, params if params else None)
        lastrowid = None
        if returning:
            row = cur.fetchone()
            lastrowid = row["id"] if row else None
        return _PgResult(cur, lastrowid)

    def executescript(self, sql: str) -> None:
        self._raw.execute(sql)  # DDL only, no parameters: psycopg runs multiple statements

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._pool.putconn(self._raw)


_pools: dict[tuple[str, str], Any] = {}


def _pool_for(target: PgTarget):
    key = (target.url, target.schema)
    if key not in _pools:
        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError:
            raise RuntimeError("Postgres mode needs `pip install \"psycopg[binary]\" psycopg_pool` (see requirements.txt).") from None

        def configure(conn):
            if target.schema:  # used by the test suite for per-test isolation; session-level, so direct connections only
                conn.execute(f'SET search_path TO "{target.schema}"')
                conn.commit()

        _pools[key] = ConnectionPool(
            target.url,
            min_size=0,  # no connection at startup: Neon may be asleep and the app must still boot
            max_size=5,
            max_idle=240,  # drop idle connections before Neon's 5-minute suspend would kill them
            timeout=10,  # also bounds /api/health when the database is unreachable
            check=ConnectionPool.check_connection,  # test a pooled connection before handing it out
            configure=configure,
            kwargs={"row_factory": dict_row, "prepare_threshold": None},  # None: safe behind PgBouncer-style poolers
            open=True,
        )
    return _pools[key]


def close_pools() -> None:
    for pool in _pools.values():
        pool.close()
    _pools.clear()
