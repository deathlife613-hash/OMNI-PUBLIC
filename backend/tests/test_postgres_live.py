"""Runs only when TEST_PG_URL points at a throwaway Postgres (e.g. a local server in Colab). NOT run by default."""
import pytest

from tests.conftest import TEST_PG_URL

pytestmark = pytest.mark.skipif(not TEST_PG_URL, reason="set TEST_PG_URL to run Postgres tests")


@pytest.fixture
def target():
    import psycopg

    from app.core import db

    schema = "t_live_layer"
    with psycopg.connect(TEST_PG_URL, autocommit=True) as c:
        c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        c.execute(f'CREATE SCHEMA "{schema}"')
    yield db.PgTarget(TEST_PG_URL, schema)
    db.close_pools()
    with psycopg.connect(TEST_PG_URL, autocommit=True) as c:
        c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_schema_is_created_idempotently_with_the_same_tables(target):
    from app.core import db

    assert db.init_db(target) == 5 and db.init_db(target) == 5
    with db.session(target) as conn:
        names = {r["table_name"] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")}
    assert {"meta", "conversations", "messages", "schema_version", "memories", "notes", "tasks", "audit_log",
            "agent_tasks", "agent_steps", "agent_approvals", "skills", "skill_versions"} <= names
    assert db.ping(target) is True


def test_constraints_cascade_lastrowid_and_explicit_ids(target):
    import psycopg

    from app.core import db

    db.init_db(target)
    with db.session(target) as conn:
        conn.execute("INSERT INTO conversations(id) VALUES ('c1')")
        cur = conn.execute("INSERT INTO messages(conversation_id, role, content) VALUES ('c1','user','hi')")
        assert isinstance(cur.lastrowid, int) and cur.lastrowid >= 1  # RETURNING id shim
        assert conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)).fetchone()["content"] == "hi"
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.session(target) as conn:
            conn.execute("INSERT INTO messages(conversation_id, role, content) VALUES ('c1','bogus','x')")
    with db.session(target) as conn:  # a failed session rolled back and left the pool usable
        assert conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 1
        conn.execute("DELETE FROM conversations WHERE id='c1'")
        assert conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 0  # ON DELETE CASCADE
    # restore-style explicit ids, then the identity counter must move past them
    with db.session(target) as conn:
        conn.execute("INSERT INTO memories(id, kind, content) VALUES (41, 'fact', 'old')")
        db.resync_sequences(conn, ("memories",))
        assert conn.execute("INSERT INTO memories(kind, content) VALUES ('fact', 'new')").lastrowid == 42


def test_dialect_features_like_conflict_timestamps_meta(target):
    from app.core import db

    db.init_db(target)
    with db.session(target) as conn:
        conn.execute("INSERT INTO notes(title, body) VALUES (?, ?)", ("Groceries", "Milk 50% off"))
        rows = conn.execute("SELECT title FROM notes WHERE title LIKE ? ESCAPE '\\'", ("%grocer%",)).fetchall()
        assert [r["title"] for r in rows] == ["Groceries"]  # LIKE is case-insensitive like SQLite
        conn.execute("INSERT OR IGNORE INTO skills(name) VALUES (?)", ("s1",))
        conn.execute("INSERT OR IGNORE INTO skills(name) VALUES (?)", ("s1",))
        assert conn.execute("SELECT COUNT(*) AS n FROM skills").fetchone()["n"] == 1
        ts = conn.execute("SELECT created_at FROM notes").fetchone()["created_at"]
        assert len(ts) == 24 and ts.endswith("Z") and ts[10] == "T"  # same ISO format SQLite writes
    db.set_meta(target, "k", "v1")
    db.set_meta(target, "k", "v2")
    assert db.get_meta(target, "k") == "v2"


def test_unreachable_database_reports_not_ok_instead_of_crashing():
    from app.core import db

    assert db.ping(db.PgTarget("postgresql://nobody:x@127.0.0.1:1/none?connect_timeout=2")) is False
    db.close_pools()
