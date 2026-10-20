def test_missing_token_rejected(make_client):
    with make_client(access_token="s3cret") as client:
        assert client.get("/api/status").status_code == 401


def test_wrong_token_rejected(make_client):
    with make_client(access_token="s3cret") as client:
        r = client.get("/api/status", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_correct_token_accepted(make_client):
    with make_client(access_token="s3cret") as client:
        r = client.get("/api/status", headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200


def test_production_without_token_fails_closed(make_client):
    with make_client(env="production", access_token="") as client:
        assert client.get("/api/status").status_code == 503
        assert client.get("/api/health").status_code == 200  # probe stays public


def test_repeated_failures_are_throttled(make_client):
    with make_client(access_token="s3cret") as client:
        codes = [
            client.get("/api/status", headers={"Authorization": "Bearer bad"}).status_code
            for _ in range(12)
        ]
        assert codes[:10] == [401] * 10
        assert codes[10] == 429
        # even the right token is blocked while throttled
        ok = client.get("/api/status", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 429
