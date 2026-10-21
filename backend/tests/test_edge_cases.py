"""Edge cases that must behave the same on SQLite and Postgres (run in both modes; see TEST_PG_URL in conftest)."""
import pytest

from app.core import db
from app.core.config import get_settings
from tests.conftest import FakeProvider

TS = "2026-01-01T00:00:00.000Z"


def target(client):
    return client.app.dependency_overrides[get_settings]().db_path


def high_id_backup():
    return {
        "format": "omni-backup", "format_version": 1,
        "conversations": [{"id": "c-high", "title": "Old chat", "created_at": TS, "updated_at": TS}],
        "messages": [{"id": 700, "conversation_id": "c-high", "role": "user", "content": "hi", "created_at": TS}],
        "memories": [{"id": 500, "kind": "fact", "content": "old fact", "enabled": 1, "created_at": TS, "updated_at": TS}],
        "notes": [{"id": 900, "title": "old note", "body": "b", "created_at": TS, "updated_at": TS}],
    }


def test_restore_with_explicit_high_ids_then_fresh_inserts_do_not_collide(make_client, monkeypatch):
    calls = []
    real = db.resync_sequences

    def spy(conn, tables):
        calls.append(tables)
        return real(conn, tables)

    monkeypatch.setattr(db, "resync_sequences", spy)  # proves restore really runs the resync step
    c = make_client(provider=FakeProvider(), ai_model="m1")
    assert c.post("/api/restore", json={"confirm": True, "backup": high_id_backup()}).status_code == 200
    assert calls == [("messages", "memories", "notes")]

    m = c.post("/api/memories", json={"content": "new fact"})
    assert m.status_code == 201 and m.json()["id"] == 501  # not 1, and no duplicate-key error
    n = c.post("/api/notes", json={"title": "new", "body": "x"})
    assert n.status_code == 201 and n.json()["id"] == 901
    r = c.post("/api/conversations/c-high/messages", json={"content": "after restore"})
    assert r.status_code == 200
    ids = [x["id"] for x in c.get("/api/conversations/c-high").json()["messages"]]
    assert ids[0] == 700 and ids[1] > 700 and len(set(ids)) == len(ids)  # new rows continue after the restored ids


def insert_version(conn, version="1.0.0", manifest="{}"):
    return conn.execute(
        "INSERT OR IGNORE INTO skill_versions(name, version, manifest, validation, created_by) VALUES (?,?,?,?,?)",
        ("s", version, manifest, "{}", "tester"),
    )


def test_ignored_insert_that_inserts_nothing_reports_zero_rows_and_leaves_the_transaction_usable(make_client):
    t = target(make_client())
    with db.session(t) as conn:
        assert insert_version(conn).rowcount == 1
        dup = insert_version(conn)  # UNIQUE(name, version) conflict -> silently ignored
        assert dup.rowcount == 0  # the caller can tell nothing was inserted
        assert conn.execute("SELECT COUNT(*) AS n FROM skill_versions").fetchone()["n"] == 1  # same transaction still works
        assert insert_version(conn, "1.0.1").rowcount == 1
    with db.session(t) as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM skill_versions").fetchone()["n"] == 2


@pytest.mark.sqlite_only
def test_sqlite_or_ignore_also_swallows_not_null_and_check_violations(make_client):
    """Documents the dialect difference: Postgres' ON CONFLICT DO NOTHING does NOT do this (see test_postgres_live)."""
    t = target(make_client())
    with db.session(t) as conn:
        assert conn.execute(
            "INSERT OR IGNORE INTO skill_versions(name, version, manifest, validation, created_by) VALUES ('a','1',NULL,'{}','x')"
        ).rowcount == 0  # NOT NULL violation ignored
        assert conn.execute(
            "INSERT OR IGNORE INTO skill_versions(name, version, manifest, validation, created_by, status) VALUES ('a','1','{}','{}','x','bogus')"
        ).rowcount == 0  # CHECK violation ignored
