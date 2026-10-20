import sqlite3

from app.core import db


def test_init_creates_schema_and_is_idempotent(tmp_path):
    path = tmp_path / "x.db"
    assert db.init_db(path) == 1
    assert db.init_db(path) == 1  # second run changes nothing
    with db.session(path) as conn:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "conversations", "messages", "schema_version"} <= tables


def test_message_cascade_and_role_check(tmp_path):
    path = tmp_path / "x.db"
    db.init_db(path)
    with db.session(path) as conn:
        conn.execute("INSERT INTO conversations(id) VALUES ('c1')")
        conn.execute("INSERT INTO messages(conversation_id, role, content) VALUES ('c1','user','hi')")
        try:
            conn.execute("INSERT INTO messages(conversation_id, role, content) VALUES ('c1','bogus','x')")
            raised = False
        except sqlite3.IntegrityError:
            raised = True
        assert raised
        conn.execute("DELETE FROM conversations WHERE id='c1'")
        assert conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 0
