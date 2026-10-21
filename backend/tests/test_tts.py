"""ElevenLabs TTS adapter against a mocked provider (no key tonight: written-not-verified against the real service)."""
import httpx

SECRET = "sk_test_SECRET_KEY_123"


def tts_client(make_client, handler=None, **extra):
    calls = []

    def default(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"ID3-fake-mp3")

    def wrapped(request: httpx.Request) -> httpx.Response:
        if handler is None:
            return default(request)
        calls.append(request)
        return handler(request)

    cfg = dict(tts_provider="elevenlabs", tts_api_key=SECRET, tts_voice_id="voice123", tts_model="m1")
    cfg.update(extra)
    c = make_client(tts_transport=httpx.MockTransport(wrapped), **cfg)
    return c, calls


def test_not_configured_is_honest_and_changes_nothing(make_client):
    c = make_client()
    st = c.get("/api/voice/status").json()
    assert st["configured"] is False and st["engine"] == "browser" and st["note"] == "TTS: not configured. Using browser voices."
    assert st["chars_used_month_estimate"] is None  # no fake numbers
    r = c.post("/api/voice/speak", json={"text": "hi"})
    assert r.status_code == 503 and r.json()["detail"]["kind"] == "not_configured"
    assert c.get("/api/status").json()["integrations"]["tts"]["configured"] is False
    assert c.get("/api/health").status_code == 200


def test_partially_configured_says_what_is_missing(make_client):
    c = make_client(tts_provider="elevenlabs", tts_api_key=SECRET)  # no voice id
    assert c.get("/api/voice/status").json()["note"] == "TTS: voice id missing. Using browser voices."
    c = make_client(tts_provider="elevenlabs", tts_voice_id="v")  # no key
    assert "API key missing" in c.get("/api/voice/status").json()["note"]
    c = make_client(tts_provider="nope", tts_api_key="k", tts_voice_id="v")
    assert "unknown provider" in c.get("/api/voice/status").json()["note"]


def test_speak_returns_audio_and_sends_the_documented_request(make_client):
    c, calls = tts_client(make_client)
    r = c.post("/api/voice/speak", json={"text": "  Hello there  "})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3-fake-mp3"
    assert r.headers["x-omni-tts-cache"] == "miss"
    req = calls[0]
    assert req.url.path == "/v1/text-to-speech/voice123" and req.headers["xi-api-key"] == SECRET
    import json

    assert json.loads(req.content) == {"text": "Hello there", "model_id": "m1"}


def test_identical_text_is_served_from_cache_and_costs_nothing(make_client):
    c, calls = tts_client(make_client)
    c.post("/api/voice/speak", json={"text": "same words"})
    r = c.post("/api/voice/speak", json={"text": "same words"})
    assert r.headers["x-omni-tts-cache"] == "hit" and len(calls) == 1
    st = c.get("/api/voice/status").json()
    assert st["cache_hits"] == 1 and st["generations"] == 1 and st["chars_used_month_estimate"] == len("same words")


def test_limits_per_reply_and_monthly_cap_protect_the_free_allowance(make_client):
    c, calls = tts_client(make_client, tts_max_chars_per_reply=10, tts_monthly_char_cap=15)
    r = c.post("/api/voice/speak", json={"text": "x" * 11})
    assert r.status_code == 413 and r.json()["detail"]["kind"] == "too_long" and not calls
    assert c.post("/api/voice/speak", json={"text": "a" * 10}).status_code == 200
    r = c.post("/api/voice/speak", json={"text": "b" * 10})  # 10 + 10 > 15
    assert r.status_code == 429 and r.json()["detail"]["kind"] == "monthly_cap" and len(calls) == 1
    assert c.post("/api/voice/speak", json={"text": "a" * 10}).status_code == 200  # cached text still free at the cap
    assert c.post("/api/voice/speak", json={"text": "   "}).status_code == 422


def test_provider_errors_become_clear_notices_and_are_not_charged_or_cached(make_client):
    for status, kind in [(401, "auth"), (402, "quota"), (429, "rate_limit"), (422, "bad_request"), (500, "unavailable")]:
        c, calls = tts_client(make_client, handler=lambda req, s=status: httpx.Response(s, text=f"boom {SECRET}"))
        r = c.post("/api/voice/speak", json={"text": "hello"})
        assert r.json()["detail"]["kind"] == kind, status
        assert SECRET not in r.text and "boom" not in r.text  # provider body/key never echoed
        st = c.get("/api/voice/status").json()
        assert st["chars_used_month_estimate"] == 0 and st["generations"] == 0


def test_timeouts_and_network_failures_are_reported(make_client):
    def boom(req):
        raise httpx.ConnectTimeout("t")

    c, _ = tts_client(make_client, handler=boom)
    assert c.post("/api/voice/speak", json={"text": "hi"}).json()["detail"]["kind"] == "timeout"

    def down(req):
        raise httpx.ConnectError("x")

    c, _ = tts_client(make_client, handler=down)
    assert c.post("/api/voice/speak", json={"text": "hi"}).json()["detail"]["kind"] == "unavailable"


def test_key_never_appears_in_status_or_settings_repr(make_client):
    c, _ = tts_client(make_client)
    assert SECRET not in c.get("/api/voice/status").text and SECRET not in c.get("/api/status").text
    from app.core.config import Settings

    assert SECRET not in repr(Settings(_env_file=None, tts_api_key=SECRET))


def test_requires_auth_when_a_token_is_set(make_client):
    c, _ = tts_client(make_client, access_token="tok")
    assert c.post("/api/voice/speak", json={"text": "hi"}).status_code == 401
    assert c.get("/api/voice/status", headers={"Authorization": "Bearer tok"}).status_code == 200
