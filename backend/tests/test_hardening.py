from tests.conftest import FakeProvider, ScriptedProvider


def test_security_headers_on_api_and_pages(make_client):
    c = make_client()
    r = c.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store" and "content-security-policy" not in r.headers
    page = c.get("/")  # no frontend built in tests -> 404, but headers still apply
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert "script-src" not in page.headers["content-security-policy"] or "unsafe-inline" not in page.headers["content-security-policy"].split("script-src")[1].split(";")[0]


def test_model_requests_are_rate_limited_locally_with_clear_message(make_client):
    c = make_client(provider=FakeProvider(), ai_model="m1", model_rpm_limit=2)
    cid = c.post("/api/conversations", json={}).json()["id"]
    for _ in range(2):
        assert c.post(f"/api/conversations/{cid}/messages", json={"content": "hi"}).status_code == 200
    r = c.post(f"/api/conversations/{cid}/messages", json={"content": "hi"})
    assert r.status_code == 429 and r.json()["detail"]["kind"] == "local_rate_limit" and int(r.headers["retry-after"]) >= 1
    # non-model routes are unaffected
    assert c.get("/api/conversations").status_code == 200
    assert c.post("/api/memories", json={"content": "still works"}).status_code == 201


def test_limiter_covers_agents_and_skills_and_not_unauthenticated(make_client):
    c = make_client(provider=ScriptedProvider(["{}"] * 10), ai_model="m1", model_rpm_limit=1)
    tid = c.post("/api/agents/tasks", json={"goal": "x"}).json()["id"]
    c.post(f"/api/agents/tasks/{tid}/run")
    assert c.post(f"/api/agents/tasks/{tid}/run").status_code == 429
    assert c.post("/api/skills/draft", json={"request": "make something"}).status_code == 429
    secured = make_client(access_token="tok", provider=FakeProvider(), ai_model="m1", model_rpm_limit=1)
    for _ in range(3):  # unauthenticated attempts must not burn the owner's budget
        assert secured.post("/api/skills/draft", json={"request": "make something"}).status_code == 401
    auth = {"Authorization": "Bearer tok"}
    assert secured.post("/api/skills/draft", json={"request": "make something"}, headers=auth).status_code != 429
