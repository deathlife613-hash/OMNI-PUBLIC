import json

from app.models.base import ChatMessage, ProviderError
from app.services.context import SYSTEM_PROMPT, build_context
from tests.conftest import FakeProvider


def parse(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        ev, data = block.split("\n", 1)
        out.append((ev[len("event: "):], json.loads(data[len("data: "):])))
    return out


def new_conv(client) -> str:
    return client.post("/api/conversations", json={}).json()["id"]


def send(client, cid, text="hi"):
    r = client.post(f"/api/conversations/{cid}/messages", json={"content": text})
    assert r.status_code == 200
    return parse(r.text)


def test_streamed_reply_is_saved_and_title_set(make_client):
    c = make_client(provider=FakeProvider(), ai_model="m1")
    cid = new_conv(c)
    evs = send(c, cid, "What is the capital of France?")
    assert [e for e, _ in evs] == ["delta", "delta", "done"]
    assert "".join(d["text"] for e, d in evs if e == "delta") == "Hello world"
    conv = c.get(f"/api/conversations/{cid}").json()
    assert [(m["role"], m["content"]) for m in conv["messages"]] == [
        ("user", "What is the capital of France?"),
        ("assistant", "Hello world"),
    ]
    assert conv["title"] == "What is the capital of France?"


def test_rate_limit_keeps_user_message_and_reports_clearly(make_client):
    err = ProviderError("rate_limit", "Rate limit reached.", retry_after=30)
    c = make_client(provider=FakeProvider(chunks=[], error=err), ai_model="m1")
    cid = new_conv(c)
    (ev, data), = send(c, cid, "hello")
    assert ev == "error" and data["kind"] == "rate_limit" and data["retry_after"] == 30
    msgs = c.get(f"/api/conversations/{cid}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user"]  # nothing lost, no fake assistant reply
    assert c.get("/api/usage").json()["rate_limit_events"] == 1


def test_not_configured_but_non_ai_features_still_work(make_client):
    c = make_client(provider=None, ai_api_key="")
    cid = new_conv(c)
    (ev, data), = send(c, cid)
    assert ev == "error" and data["kind"] == "not_configured"
    assert c.get("/api/conversations").status_code == 200
    assert c.patch(f"/api/conversations/{cid}", json={"title": "Renamed"}).json()["title"] == "Renamed"
    assert c.delete(f"/api/conversations/{cid}").status_code == 204
    assert c.get(f"/api/conversations/{cid}").status_code == 404


def test_no_model_selected_error(make_client):
    c = make_client(provider=FakeProvider(), ai_model="")
    (ev, data), = send(c, new_conv(c))
    assert ev == "error" and data["kind"] == "no_model"


def test_model_selection_validates_and_is_used(make_client):
    fake = FakeProvider()
    c = make_client(provider=fake, ai_model="")
    assert c.put("/api/provider/model", json={"model": "nope"}).status_code == 400
    assert c.put("/api/provider/model", json={"model": "m2"}).status_code == 200
    assert c.get("/api/provider").json()["model"] == "m2"
    send(c, new_conv(c))
    assert fake.calls[0][1] == "m2"


def test_connection_test_updates_status(make_client):
    c = make_client(provider=FakeProvider())
    assert c.get("/api/status").json()["ai"]["connected"] is None  # never faked
    r = c.post("/api/provider/test").json()
    assert r["ok"] is True and r["models_available"] == 2
    assert c.get("/api/status").json()["ai"]["connected"] is True


def test_connection_test_failure_is_reported(make_client):
    c = make_client(provider=FakeProvider(chunks=[], error=ProviderError("auth", "bad key")))
    r = c.post("/api/provider/test").json()
    assert r["ok"] is False and r["kind"] == "auth"
    assert c.get("/api/status").json()["ai"]["connected"] is False


def test_provider_info_hides_key_and_blocks_paid_by_default(make_client):
    c = make_client(ai_api_key="sk-secret-123")
    r = c.get("/api/provider")
    assert "sk-secret-123" not in r.text
    assert r.json()["paid_providers_allowed"] is False and r.json()["api_key_configured"] is True


def test_chat_routes_require_auth(make_client):
    c = make_client(access_token="tok")
    assert c.get("/api/conversations").status_code == 401
    assert c.post("/api/conversations", json={}).status_code == 401
    assert c.post("/api/provider/test").status_code == 401
    assert c.get("/api/conversations", headers={"Authorization": "Bearer tok"}).status_code == 200


def test_context_keeps_newest_within_budget():
    hist = [ChatMessage("user", "a" * 100), ChatMessage("assistant", "b" * 100), ChatMessage("user", "c" * 100)]
    ctx = build_context(hist, budget_chars=len(SYSTEM_PROMPT) + 150)
    assert ctx[0].role == "system"
    assert [m.content[0] for m in ctx[1:]] == ["c"]  # older messages dropped, newest kept


def test_context_always_keeps_latest_even_if_over_budget():
    ctx = build_context([ChatMessage("user", "x" * 500)], budget_chars=10)
    assert len(ctx) == 2 and ctx[1].content == "x" * 500


def test_input_validation(make_client):
    c = make_client(provider=FakeProvider(), ai_model="m1")
    cid = new_conv(c)
    assert c.post(f"/api/conversations/{cid}/messages", json={"content": ""}).status_code == 422
    assert c.post(f"/api/conversations/{cid}/messages", json={"content": "x" * 9000}).status_code == 422
    assert c.post("/api/conversations/missing/messages", json={"content": "hi"}).status_code == 404
