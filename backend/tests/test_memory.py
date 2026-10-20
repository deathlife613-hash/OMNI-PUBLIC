from app.models.base import ChatMessage
from app.services.context import build_context
from tests.conftest import FakeProvider


def add(c, text, kind="fact"):
    r = c.post("/api/memories", json={"content": text, "kind": kind})
    assert r.status_code == 201
    return r.json()["id"]


def test_memory_crud_and_disable(make_client):
    c = make_client()
    mid = add(c, "My cat is named Pixel")
    assert c.patch(f"/api/memories/{mid}", json={"content": "My cat is named Pixel II"}).json()["content"].endswith("II")
    assert c.patch(f"/api/memories/{mid}", json={"enabled": False}).json()["enabled"] is False
    assert [m["id"] for m in c.get("/api/memories", params={"q": "pixel"}).json()] == [mid]
    assert c.get("/api/memories", params={"q": "dog"}).json() == []
    assert c.delete(f"/api/memories/{mid}").status_code == 204
    assert c.delete(f"/api/memories/{mid}").status_code == 404
    assert c.patch("/api/memories/999", json={"enabled": True}).status_code == 404


def test_secrets_are_refused_everywhere(make_client):
    c = make_client()
    assert c.post("/api/memories", json={"content": "my key is gsk_abcdefghijklmnop1234"}).status_code == 422
    assert c.post("/api/memories", json={"content": "password: hunter2"}).status_code == 422
    assert c.post("/api/notes", json={"title": "k", "body": "sk-abcdefghijklmnopqrstuv"}).status_code == 422
    mid = add(c, "harmless")
    assert c.patch(f"/api/memories/{mid}", json={"content": "api_key = abc"}).status_code == 422


def test_notes_crud_and_search(make_client):
    c = make_client()
    nid = c.post("/api/notes", json={"title": "Groceries", "body": "milk and eggs"}).json()["id"]
    assert c.get("/api/notes", params={"q": "eggs"}).json()[0]["id"] == nid
    assert c.get("/api/notes", params={"q": "100%"}).json() == []  # LIKE wildcards are escaped
    assert c.patch(f"/api/notes/{nid}", json={"body": "milk"}).json()["body"] == "milk"
    assert c.delete(f"/api/notes/{nid}").status_code == 204
    assert c.get("/api/notes").json() == []


def test_memories_reach_model_only_when_relevant_and_enabled(make_client):
    fake = FakeProvider()
    c = make_client(provider=fake, ai_model="m1")
    add(c, "I prefer short answers", "preference")
    add(c, "My cat is named Pixel")
    off = add(c, "My dog is named Rex")
    c.patch(f"/api/memories/{off}", json={"enabled": False})
    add(c, "I live in Minnesota")
    cid = c.post("/api/conversations", json={}).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"content": "what is my cat called?"})
    system = fake.calls[0][0][0].content
    assert "I prefer short answers" in system and "Pixel" in system
    assert "Rex" not in system and "Minnesota" not in system  # disabled / irrelevant not sent


def test_memory_master_switch_off_sends_nothing(make_client):
    fake = FakeProvider()
    c = make_client(provider=fake, ai_model="m1")
    add(c, "I prefer short answers", "preference")
    assert c.put("/api/memory/settings", json={"enabled": False}).json() == {"enabled": False}
    cid = c.post("/api/conversations", json={}).json()["id"]
    c.post(f"/api/conversations/{cid}/messages", json={"content": "hi"})
    assert "short answers" not in fake.calls[0][0][0].content


def test_context_includes_memory_block_and_counts_it():
    ctx = build_context([ChatMessage("user", "hi")], 100000, ["fact one"])
    assert "Saved memories" in ctx[0].content and "- fact one" in ctx[0].content


def test_export_restore_roundtrip_and_survives_new_app(make_client, tmp_path):
    c = make_client()
    cid = c.post("/api/conversations", json={"title": "T"}).json()["id"]
    add(c, "remember me")
    c.post("/api/notes", json={"title": "N", "body": "b"})
    backup = c.get("/api/export").json()
    assert backup["format"] == "omni-backup" and "access_token" not in str(backup)
    # wipe, then restore
    c.delete(f"/api/conversations/{cid}")
    c.delete("/api/memories/1")
    assert c.post("/api/restore", json={"backup": backup}).status_code == 400  # needs confirm
    r = c.post("/api/restore", json={"confirm": True, "backup": backup})
    assert r.json()["restored"]["memories"] == 1
    assert c.get("/api/memories").json()[0]["content"] == "remember me"
    assert c.get(f"/api/conversations/{cid}").status_code == 200


def test_restore_rejects_bad_backup_and_changes_nothing(make_client):
    c = make_client()
    add(c, "keep me")
    assert c.post("/api/restore", json={"confirm": True, "backup": {"format": "x"}}).status_code == 422
    bad = {"format": "omni-backup", "format_version": 1, "conversations": [{"id": "a"}], "messages": [], "memories": [], "notes": []}
    assert c.post("/api/restore", json={"confirm": True, "backup": bad}).status_code == 422
    assert [m["content"] for m in c.get("/api/memories").json()] == ["keep me"]  # rolled back


def test_persists_across_app_restart(make_client):
    c1 = make_client()
    add(c1, "durable fact")
    c2 = make_client()  # brand-new app object, same db file
    assert c2.get("/api/memories").json()[0]["content"] == "durable fact"


def test_memory_routes_require_auth(make_client):
    c = make_client(access_token="tok")
    for path in ("/api/memories", "/api/notes", "/api/export"):
        assert c.get(path).status_code == 401
