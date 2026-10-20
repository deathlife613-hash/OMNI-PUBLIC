import asyncio
import json

import httpx
import pytest

from app.models.base import ChatMessage, ProviderError
from app.models.openai_compat import OpenAICompatProvider


def sse(*chunks: str) -> str:
    body = "".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks)
    return body + "data: [DONE]\n\n"


def make(handler, **kw) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        "groq", "https://x.test/v1", "SECRET-KEY", transport=httpx.MockTransport(handler), backoff_base=0, **kw
    )


async def collect(p, model="m1"):
    return [e.delta async for e in p.stream_chat([ChatMessage("user", "hi")], model, 50) if e.delta]


def run(coro):
    return asyncio.run(coro)


def test_streams_text_and_sends_auth_header_and_payload():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, text=sse("Hel", "lo"))

    assert run(collect(make(handler))) == ["Hel", "lo"]
    assert seen["auth"] == "Bearer SECRET-KEY"
    assert seen["body"]["stream"] is True and seen["body"]["max_tokens"] == 50


def test_429_is_never_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "slow down"}})

    with pytest.raises(ProviderError) as ei:
        run(collect(make(handler)))
    assert ei.value.kind == "rate_limit" and ei.value.retry_after == 7
    assert len(calls) == 1
    assert "paid plan" in ei.value.message


def test_5xx_retried_then_succeeds():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503, text="down") if len(calls) < 3 else httpx.Response(200, text=sse("ok"))

    assert run(collect(make(handler))) == ["ok"]
    assert len(calls) == 3


def test_5xx_retries_are_bounded():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(500, text="boom")

    with pytest.raises(ProviderError) as ei:
        run(collect(make(handler, max_retries=2)))
    assert ei.value.kind == "unavailable"
    assert len(calls) == 3  # 1 try + 2 retries, then stop


def test_timeout_maps_to_timeout_error():
    def handler(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ProviderError) as ei:
        run(collect(make(handler, max_retries=1)))
    assert ei.value.kind == "timeout"


def test_auth_error_does_not_leak_key():
    def handler(req):
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    with pytest.raises(ProviderError) as ei:
        run(collect(make(handler)))
    assert ei.value.kind == "auth" and "SECRET-KEY" not in ei.value.message


def test_quota_402():
    def handler(req):
        return httpx.Response(402, json={"error": {"message": "credits"}})

    with pytest.raises(ProviderError) as ei:
        run(collect(make(handler)))
    assert ei.value.kind == "quota"


def test_list_models_sorted_and_context_window():
    def handler(req):
        assert req.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "b", "context_window": 8192}, {"id": "a"}]})

    models = run(make(handler).list_models())
    assert [m.id for m in models] == ["a", "b"]
    assert models[1].context_window == 8192 and models[0].context_window is None


def test_free_only_filters_models_and_blocks_paid_without_http_call():
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={"data": [{"id": "x/y:free"}, {"id": "x/z"}]})

    p = make(handler, free_only=lambda m: m.endswith(":free"))
    assert [m.id for m in run(p.list_models())] == ["x/y:free"]
    calls.clear()
    with pytest.raises(ProviderError) as ei:
        run(collect(p, model="x/z"))
    assert ei.value.kind == "paid_blocked"
    assert calls == []  # no request was made


def test_allow_paid_flag_lifts_the_guard():
    p = make(lambda r: httpx.Response(200, text=sse("ok")), free_only=lambda m: False, allow_paid=True)
    assert run(collect(p, model="paid-model")) == ["ok"]
