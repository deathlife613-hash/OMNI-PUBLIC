import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.models.base import ChatMessage, ProviderError
from app.models.registry import PRESETS, build_provider


def cfg(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def run(coro):
    return asyncio.run(coro)


def test_all_four_providers_are_registered():
    assert {"groq", "openrouter", "ollama", "huggingface"} <= set(PRESETS)


def test_ollama_cloud_needs_a_key_but_local_does_not():
    with pytest.raises(ProviderError) as ei:
        build_provider(cfg(ai_provider="ollama"))
    assert ei.value.kind == "not_configured"
    assert build_provider(cfg(ai_provider="ollama", ai_api_key="k")).name == "ollama"
    assert build_provider(cfg(ai_provider="ollama", ai_base_url="http://localhost:11434/v1")).name == "ollama"


def test_huggingface_requires_a_key():
    with pytest.raises(ProviderError):
        build_provider(cfg(ai_provider="huggingface"))


@pytest.mark.parametrize(
    "provider,host",
    [("ollama", "ollama.com"), ("huggingface", "router.huggingface.co")],
)
def test_adapters_hit_the_right_endpoint_hide_non_chat_models_and_stream(provider, host):
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.method, req.url.host, req.url.path, req.headers["authorization"]))
        if req.url.path.endswith("/models"):
            data = [{"id": "gpt-oss:120b"}, {"id": "whisper-large-v3"}, {"id": "nomic-embed-text"}]
            return httpx.Response(200, json={"data": data})
        body = "".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in ("Hi", "!"))
        return httpx.Response(200, text=body + "data: [DONE]\n\n")

    p = build_provider(cfg(ai_provider=provider, ai_api_key="KEY"), transport=httpx.MockTransport(handler))
    assert [m.id for m in run(p.list_models())] == ["gpt-oss:120b"]

    async def chat():
        return [e.delta async for e in p.stream_chat([ChatMessage("user", "x")], "gpt-oss:120b", 20) if e.delta]

    assert run(chat()) == ["Hi", "!"]
    assert all(h == host and auth == "Bearer KEY" for _, h, _, auth in seen)
    assert seen[0][2] == "/v1/models" and seen[1][2] == "/v1/chat/completions"


def test_huggingface_402_is_reported_as_quota_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(402, json={"error": "You have exceeded your monthly included credits"})

    p = build_provider(cfg(ai_provider="huggingface", ai_api_key="k"), transport=httpx.MockTransport(handler))

    async def chat():
        return [e async for e in p.stream_chat([ChatMessage("user", "x")], "m", 20)]

    with pytest.raises(ProviderError) as ei:
        run(chat())
    assert ei.value.kind == "quota" and len(calls) == 1
