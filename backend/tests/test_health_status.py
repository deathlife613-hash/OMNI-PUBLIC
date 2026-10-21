def test_health_ok_and_initializes_db(make_client, tmp_path):
    with make_client() as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert (tmp_path / "test.db").exists()


def test_health_reveals_no_config(make_client):
    with make_client(access_token="secret-token", ai_api_key="sk-live-123") as client:
        text = client.get("/api/health").text
    assert "secret-token" not in text and "sk-live-123" not in text


def test_status_never_leaks_secrets(make_client):
    with make_client(access_token="secret-token", ai_api_key="sk-live-123") as client:
        r = client.get("/api/status", headers={"Authorization": "Bearer secret-token"})
    assert r.status_code == 200
    assert "secret-token" not in r.text and "sk-live-123" not in r.text
    ai = r.json()["ai"]
    assert ai["api_key_configured"] is True
    assert ai["connected"] is None  # unknown, not faked
    assert ai["paid_providers_allowed"] is False


def test_status_reports_unavailable_as_null_not_fake(make_client):
    with make_client() as client:
        body = client.get("/api/status").json()
    assert body["ai"]["model"] == "openai/gpt-oss-120b"  # configured default, not a measurement
    assert body["ai"]["connected"] is None  # never claimed until a real test succeeds
    assert body["ai"]["api_key_configured"] is False
    assert body["database"]["ok"] is True
    with make_client(ai_model="") as client:  # explicit "no default" still reports null
        assert client.get("/api/status").json()["ai"]["model"] is None


def test_status_reports_integrations_without_secrets(make_client):
    c = make_client(search_provider="tavily", search_api_key="tvly-SECRETSECRETSECRET")
    r = c.get("/api/status")
    assert r.json()["integrations"] == {"search": {"configured": True, "provider": "tavily"}, "documents": {"enabled": False}}
    assert "SECRETSECRET" not in r.text
