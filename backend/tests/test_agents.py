import json
import os

import pytest

from app.models.base import ProviderError
from tests.conftest import ScriptedProvider


def plan(*steps):
    return json.dumps({"steps": [{"role": r, "instruction": i} for r, i in steps]})


def drive(c, tid):
    r = c.post(f"/api/agents/tasks/{tid}/run")
    assert r.status_code == 200, r.text
    return [l[7:] for l in r.text.splitlines() if l.startswith("event: ")]


def new(c, goal="Plan my week"):
    return c.post("/api/agents/tasks", json={"goal": goal}).json()["id"]


def task(c, tid):
    return c.get(f"/api/agents/tasks/{tid}").json()


def test_happy_path_is_sequential_bounded_and_checkpointed(make_client):
    prov = ScriptedProvider([plan(("planning", "make a plan"), ("review", "review it")), "PLAN OUT", "REVIEW OUT", "SUMMARY"])
    c = make_client(provider=prov, ai_model="m1")
    tid = new(c)
    evs = drive(c, tid)
    t = task(c, tid)
    assert t["status"] == "succeeded" and t["summary"] == "SUMMARY"
    assert t["model_calls"] == 4 == len(prov.calls)  # plan + 2 steps + summary
    assert [s["output"] for s in t["steps"]] == ["PLAN OUT", "REVIEW OUT"]
    assert "done" in evs
    # earlier output is passed to later steps
    assert "PLAN OUT" in prov.calls[2][1].content


def test_limits_endpoint_is_honest(make_client):
    lim = make_client().get("/api/agents/limits").json()
    assert lim["command_execution"] is False and "sequential" in lim["execution"]
    assert "testing" in lim["not_enabled"]


def test_invalid_plan_executes_nothing(make_client):
    for bad in ("not json", plan(("hacker", "x")), json.dumps({"steps": []}), plan(*[("planning", "s")] * 7), plan(("coding", "x"))):
        c = make_client(provider=ScriptedProvider([bad]), ai_model="m1")
        tid = new(c)
        drive(c, tid)
        t = task(c, tid)
        assert t["status"] == "failed" and t["steps"] == [] and "invalid" in t["error"], bad


def test_model_call_budget_stops_the_run(make_client):
    prov = ScriptedProvider([plan(("planning", "a"), ("planning", "b"), ("planning", "c")), "o1", "o2", "o3", "s"])
    c = make_client(provider=prov, ai_model="m1", agent_max_model_calls=3)
    tid = new(c)
    drive(c, tid)
    t = task(c, tid)
    assert t["status"] == "failed" and "budget" in t["error"].lower()
    assert t["model_calls"] == 3 and len(prov.calls) == 3  # never exceeded


def test_quota_pauses_then_resume_continues_without_replanning(make_client):
    prov = ScriptedProvider([
        plan(("planning", "a"), ("review", "b")), "OUT A",
        ProviderError("rate_limit", "Rate limit reached."),
        "OUT B", "SUM",
    ])
    c = make_client(provider=prov, ai_model="m1")
    tid = new(c)
    drive(c, tid)
    t = task(c, tid)
    assert t["status"] == "paused_quota" and "resume" in t["error"].lower()
    assert [s["status"] for s in t["steps"]] == ["succeeded", "queued"]  # state preserved
    drive(c, tid)
    t = task(c, tid)
    assert t["status"] == "succeeded" and [s["output"] for s in t["steps"]] == ["OUT A", "OUT B"]
    assert len(prov.calls) == 5  # plan was NOT repeated


def test_cancel_before_run_and_during_run(make_client):
    c = make_client(provider=ScriptedProvider([]), ai_model="m1")
    tid = new(c)
    assert c.post(f"/api/agents/tasks/{tid}/cancel").status_code == 200
    assert task(c, tid)["status"] == "cancelled"
    assert c.post(f"/api/agents/tasks/{tid}/run").status_code == 409
    # cancel requested while running: honoured at the next model call
    prov = ScriptedProvider([plan(("planning", "a")), "x", "s"])
    c2 = make_client(provider=prov, ai_model="m1")
    t2 = new(c2)
    import sqlite3

    orig = prov.stream_chat

    async def hook(messages, model, max_tokens):
        if len(prov.calls) == 1:  # after the plan call, request cancel
            con = sqlite3.connect(c2.app.dependency_overrides[__import__("app.core.config", fromlist=["x"]).get_settings]().db_path)
            con.execute("UPDATE agent_tasks SET cancel_requested = 1"); con.commit(); con.close()
        async for e in orig(messages, model, max_tokens):
            yield e

    prov.stream_chat = hook
    drive(c2, t2)
    assert task(c2, t2)["status"] == "cancelled"


def test_provider_error_kinds_map_to_failed_or_paused(make_client):
    cases = {"auth": "failed", "unavailable": "paused", "timeout": "paused", "quota": "paused_quota"}
    for kind, status in cases.items():
        c = make_client(provider=ScriptedProvider([ProviderError(kind, "boom")]), ai_model="m1")
        tid = new(c)
        drive(c, tid)
        assert task(c, tid)["status"] == status, kind


def test_no_provider_configured_fails_clearly(make_client):
    c = make_client(provider=None, ai_api_key="")
    tid = new(c)
    drive(c, tid)
    assert task(c, tid)["status"] == "failed"


def test_one_task_at_a_time(make_client):
    c = make_client(provider=ScriptedProvider([]), ai_model="m1")
    a, b = new(c), new(c)
    import sqlite3

    from app.core.config import get_settings

    path = c.app.dependency_overrides[get_settings]().db_path
    con = sqlite3.connect(path)
    con.execute("UPDATE agent_tasks SET status='running', updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (a,))
    con.commit(); con.close()
    assert c.post(f"/api/agents/tasks/{b}/run").status_code == 409


def test_run_finished_task_is_rejected_and_delete_works(make_client):
    c = make_client(provider=ScriptedProvider([plan(("planning", "a")), "o", "s"]), ai_model="m1")
    tid = new(c)
    drive(c, tid)
    assert c.post(f"/api/agents/tasks/{tid}/run").status_code == 409
    assert c.delete(f"/api/agents/tasks/{tid}").status_code == 204
    assert c.get(f"/api/agents/tasks/{tid}").status_code == 404


def test_research_step_uses_search_and_records_sources(make_client):
    from tests.conftest import FakeSearch

    prov = ScriptedProvider([plan(("research", "find x")), "found", "s"])
    c = make_client(provider=prov, search=FakeSearch(), ai_model="m1")
    tid = new(c)
    drive(c, tid)
    assert "UNTRUSTED" in prov.calls[1][1].content and "https://a.example/x" in prov.calls[1][1].content
    assert "https://a.example/x" in task(c, tid)["steps"][0]["sources"]


# ---------------- coding workspace ----------------
@pytest.fixture
def wsdir(tmp_path):
    d = tmp_path / "proj"
    (d / "src").mkdir(parents=True)
    (d / "src" / "app.py").write_text("print('v1')\n")
    (d / ".env").write_text("KEY=1")
    (tmp_path / "outside.py").write_text("orig")
    return d


def coding_run(c, changes, notes="n"):
    return json.dumps({"notes": notes, "changes": changes})


def test_workspace_is_read_only_viewer_and_blocks_escape(make_client, wsdir):
    c = make_client(workspace_dir=wsdir)
    assert c.get("/api/workspace/tree").json()["files"] == ["src/app.py"]  # .env hidden
    assert c.get("/api/workspace/file", params={"path": "src/app.py"}).json()["text"] == "print('v1')\n"
    for bad in ("../outside.py", "/etc/passwd", ".env", "src/../../outside.py", "src/app.exe", "C:\\x.py"):
        assert c.get("/api/workspace/file", params={"path": bad}).status_code == 400, bad
    assert make_client().get("/api/workspace/tree").status_code == 400  # no workspace configured


def test_coding_step_creates_pending_diff_and_writes_nothing(make_client, wsdir):
    prov = ScriptedProvider([plan(("coding", "change app.py")), coding_run([{"path": "src/app.py", "new_content": "print('v2')\n"}]), "SUM"])
    c = make_client(provider=prov, ai_model="m1", workspace_dir=wsdir)
    tid = new(c)
    drive(c, tid)
    t = task(c, tid)
    assert t["status"] == "waiting_approval"
    assert (wsdir / "src" / "app.py").read_text() == "print('v1')\n"  # untouched until approved
    ap = c.get("/api/agents/approvals").json()
    assert len(ap) == 1 and "-print('v1')" in ap[0]["diff"] and "+print('v2')" in ap[0]["diff"]


def test_approve_applies_then_revert_restores(make_client, wsdir):
    prov = ScriptedProvider([plan(("coding", "x")), coding_run([{"path": "src/app.py", "new_content": "print('v2')\n"}, {"path": "src/new.py", "new_content": "a=1\n"}]), "SUM"])
    c = make_client(provider=prov, ai_model="m1", workspace_dir=wsdir)
    tid = new(c)
    drive(c, tid)
    ids = [a["id"] for a in c.get("/api/agents/approvals").json()]
    assert c.post(f"/api/agents/approvals/{ids[0]}/approve").status_code == 200
    assert (wsdir / "src" / "app.py").read_text() == "print('v2')\n"
    assert task(c, tid)["status"] == "waiting_approval"  # one still pending
    assert c.post(f"/api/agents/approvals/{ids[1]}/reject").status_code == 200
    assert not (wsdir / "src" / "new.py").exists()
    assert task(c, tid)["status"] == "succeeded"
    assert c.post(f"/api/agents/approvals/{ids[0]}/approve").status_code == 409  # not twice
    assert c.post(f"/api/agents/approvals/{ids[0]}/revert").status_code == 200
    assert (wsdir / "src" / "app.py").read_text() == "print('v1')\n"


def test_revert_refuses_to_clobber_newer_edits_and_new_file_revert_deletes(make_client, wsdir):
    prov = ScriptedProvider([plan(("coding", "x")), coding_run([{"path": "src/new.py", "new_content": "a=1\n"}]), "SUM"])
    c = make_client(provider=prov, ai_model="m1", workspace_dir=wsdir)
    tid = new(c)
    drive(c, tid)
    aid = c.get("/api/agents/approvals").json()[0]["id"]
    c.post(f"/api/agents/approvals/{aid}/approve")
    (wsdir / "src" / "new.py").write_text("user edit\n")
    assert c.post(f"/api/agents/approvals/{aid}/revert").status_code == 409
    (wsdir / "src" / "new.py").write_text("a=1\n")
    assert c.post(f"/api/agents/approvals/{aid}/revert").status_code == 200
    assert not (wsdir / "src" / "new.py").exists()


def test_stale_proposal_cannot_be_applied(make_client, wsdir):
    prov = ScriptedProvider([plan(("coding", "x")), coding_run([{"path": "src/app.py", "new_content": "print('v2')\n"}]), "SUM"])
    c = make_client(provider=prov, ai_model="m1", workspace_dir=wsdir)
    tid = new(c)
    drive(c, tid)
    (wsdir / "src" / "app.py").write_text("print('someone else')\n")
    aid = c.get("/api/agents/approvals").json()[0]["id"]
    assert c.post(f"/api/agents/approvals/{aid}/approve").status_code == 409
    assert (wsdir / "src" / "app.py").read_text() == "print('someone else')\n"


@pytest.mark.parametrize("path", ["../outside.py", "/tmp/x.py", ".env", "src/key.pem", ".git/config", "src/a.exe", "missing_dir/x.py"])
def test_coding_agent_cannot_target_unsafe_paths(make_client, wsdir, path):
    prov = ScriptedProvider([plan(("coding", "x")), coding_run([{"path": path, "new_content": "x"}])])
    c = make_client(provider=prov, ai_model="m1", workspace_dir=wsdir)
    tid = new(c)
    drive(c, tid)
    t = task(c, tid)
    assert t["status"] == "failed" and c.get("/api/agents/approvals").json() == []
    assert (wsdir.parent / "outside.py").read_text() == "orig"


def test_secrets_in_proposals_are_rejected(make_client, wsdir):
    prov = ScriptedProvider([plan(("coding", "x")), coding_run([{"path": "src/a.py", "new_content": "KEY='gsk_abcdefghijklmnop1234'"}])])
    c = make_client(provider=prov, ai_model="m1", workspace_dir=wsdir)
    tid = new(c)
    drive(c, tid)
    assert task(c, tid)["status"] == "failed" and c.get("/api/agents/approvals").json() == []


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_symlink_in_workspace_is_blocked(make_client, wsdir, tmp_path):
    os.symlink(tmp_path / "outside.py", wsdir / "src" / "link.py")
    c = make_client(workspace_dir=wsdir)
    assert c.get("/api/workspace/file", params={"path": "src/link.py"}).status_code == 400
    assert "link.py" not in c.get("/api/workspace/tree").text


def test_garbage_coding_output_fails_safely(make_client, wsdir):
    prov = ScriptedProvider([plan(("coding", "x")), "sure! here you go"])
    c = make_client(provider=prov, ai_model="m1", workspace_dir=wsdir)
    tid = new(c)
    drive(c, tid)
    assert task(c, tid)["status"] == "failed"


def test_too_many_changes_rejected(make_client, wsdir):
    ch = [{"path": f"src/f{i}.py", "new_content": "x"} for i in range(4)]
    c = make_client(provider=ScriptedProvider([plan(("coding", "x")), coding_run(ch)]), ai_model="m1", workspace_dir=wsdir)
    tid = new(c)
    drive(c, tid)
    assert task(c, tid)["status"] == "failed" and c.get("/api/agents/approvals").json() == []


def test_agent_routes_require_auth(make_client):
    c = make_client(access_token="tok")
    for method, path in (("get", "/api/agents/tasks"), ("post", "/api/agents/tasks"), ("get", "/api/agents/approvals"), ("get", "/api/workspace/tree")):
        assert getattr(c, method)(path).status_code == 401
