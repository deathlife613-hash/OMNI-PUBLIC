import os

import pytest


def run(c, name, args=None, confirm=False):
    return c.post(f"/api/tools/{name}/run", json={"args": args or {}, "confirm": confirm})


def test_list_tools_has_schemas_and_flags_destructive(make_client):
    tools = {t["name"]: t for t in make_client().get("/api/tools").json()}
    assert {"calculator", "task_add", "doc_search", "reminder_add"} <= set(tools)
    assert tools["task_delete"]["needs_confirmation"] is True
    assert tools["calculator"]["input_schema"]["properties"]["expression"]


@pytest.mark.parametrize("expr,expected", [("2+3*4", 14), ("(1+2)**3", 27), ("sqrt(16)+abs(-2)", 6.0), ("10//3", 3), ("-2**2", -4)])
def test_calculator_works(make_client, expr, expected):
    assert run(make_client(), "calculator", {"expression": expr}).json()["result"]["result"] == expected


@pytest.mark.parametrize("expr", ["__import__('os').system('id')", "open('x')", "a+1", "9**9**9", "10**5000", "1/0", "2+", "'a'*5", "().__class__"])
def test_calculator_rejects_unsafe_or_bad_input(make_client, expr):
    r = run(make_client(), "calculator", {"expression": expr})
    assert r.status_code == 400


def test_input_validation(make_client):
    c = make_client()
    assert run(c, "calculator", {}).status_code == 422
    assert run(c, "calculator", {"expression": "x" * 500}).status_code == 422
    assert run(c, "nope").status_code == 404


def test_datetime_and_bad_timezone(make_client):
    c = make_client()
    r = run(c, "current_datetime", {"timezone": "America/Chicago"}).json()["result"]
    assert r["timezone"] == "America/Chicago" and r["weekday"]
    assert run(c, "current_datetime", {"timezone": "Mars/Base"}).status_code == 400


def test_tasks_lifecycle_and_delete_needs_confirmation(make_client):
    c = make_client()
    tid = run(c, "task_add", {"title": "Pay rent", "due_at": "2026-11-01T09:00:00Z"}).json()["result"]["id"]
    assert run(c, "task_list").json()["result"][0]["title"] == "Pay rent"
    assert run(c, "task_complete", {"id": tid}).json()["result"]["done"] is True
    r = run(c, "task_delete", {"id": tid})
    assert r.status_code == 409 and r.json()["detail"]["kind"] == "needs_confirmation"
    assert run(c, "task_list").json()["result"]  # still there
    assert run(c, "task_delete", {"id": tid}, confirm=True).status_code == 200
    assert run(c, "task_list").json()["result"] == []
    assert run(c, "task_complete", {"id": 99}).status_code == 400


def test_bad_dates_rejected(make_client):
    assert run(make_client(), "task_add", {"title": "x", "due_at": "tomorrow"}).status_code == 400


def test_reminders_due_only_when_past_and_not_done(make_client):
    c = make_client()
    past = run(c, "reminder_add", {"title": "old", "remind_at": "2020-01-01T00:00:00Z"}).json()["result"]["id"]
    run(c, "reminder_add", {"title": "future", "remind_at": "2999-01-01T00:00:00Z"})
    assert [r["title"] for r in run(c, "reminders_due").json()["result"]] == ["old"]
    run(c, "task_complete", {"id": past})
    assert run(c, "reminders_due").json()["result"] == []


def test_notes_tools_and_secret_refusal(make_client):
    c = make_client()
    run(c, "note_add", {"title": "Plan", "body": "buy milk"})
    assert run(c, "note_search", {"query": "milk"}).json()["result"][0]["title"] == "Plan"
    assert run(c, "note_add", {"title": "k", "body": "gsk_abcdefghijklmnop1234"}).status_code == 400


def test_docs_disabled_by_default(make_client):
    assert run(make_client(), "doc_search", {"query": "x"}).status_code == 400


@pytest.fixture
def docs(tmp_path):
    d = tmp_path / "docs"
    (d / "sub").mkdir(parents=True)
    (d / "a.md").write_text("The quarterly budget is approved.")
    (d / "sub" / "b.txt").write_text("nothing here")
    (d / ".env").write_text("SECRET=1 budget")
    (d / "notes.pem").write_text("budget key")
    (d / "bin.exe").write_text("budget")
    (tmp_path / "outside.txt").write_text("budget outside")
    return d


def test_doc_search_finds_only_authorized_safe_files(make_client, docs):
    c = make_client(docs_dir=docs)
    res = run(c, "doc_search", {"query": "budget"}).json()["result"]
    assert [h["path"] for h in res["results"]] == ["a.md"]
    assert "untrusted" in res["notice"]


def test_doc_read_blocks_traversal_secrets_and_other_types(make_client, docs):
    c = make_client(docs_dir=docs)
    assert run(c, "doc_read", {"path": "a.md"}).json()["result"]["text"].startswith("The quarterly")
    for bad in ("../outside.txt", "/etc/passwd", ".env", "notes.pem", "bin.exe", "missing.md", "sub/../../outside.txt"):
        assert run(c, "doc_read", {"path": bad}).status_code == 400, bad


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_symlink_escape_blocked(make_client, docs, tmp_path):
    os.symlink(tmp_path / "outside.txt", docs / "link.txt")
    c = make_client(docs_dir=docs)
    assert run(c, "doc_read", {"path": "link.txt"}).status_code == 400
    assert "link.txt" not in str(run(c, "doc_search", {"query": "budget"}).json())


def test_audit_log_records_outcomes_without_arguments(make_client):
    c = make_client()
    run(c, "calculator", {"expression": "1+1"})
    run(c, "calculator", {"expression": "bad("})
    log = c.get("/api/audit").json()
    assert [(e["tool"], e["outcome"]) for e in log][:2] == [("calculator", "refused"), ("calculator", "ok")]
    assert "1+1" not in str(log)


def test_tools_require_auth(make_client):
    c = make_client(access_token="tok")
    assert c.get("/api/tools").status_code == 401
    assert c.post("/api/tools/calculator/run", json={"args": {"expression": "1"}}).status_code == 401
