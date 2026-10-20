"""Adapter for OpenAI-compatible APIs (Groq, OpenRouter, ...).

Bounded retries: only for timeouts / 5xx, only before any text has been sent,
at most `max_retries` times with exponential backoff. A 429 is NEVER retried
automatically because retries can burn the free daily quota.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Callable

import httpx

from app.models.base import (
    ChatMessage,
    ModelInfo,
    Provider,
    ProviderError,
    StreamEvent,
    TokenUsage,
)


def _short(text: str, n: int = 200) -> str:
    return text if len(text) <= n else text[:n] + "…"


class OpenAICompatProvider(Provider):
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 60,
        max_retries: int = 2,
        backoff_base: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
        free_only: Callable[[str], bool] | None = None,
        allow_paid: bool = False,
    ):
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff_base
        self._transport = transport
        self._free_only = free_only
        self._allow_paid = allow_paid

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )

    def _is_allowed(self, model_id: str) -> bool:
        return self._allow_paid or self._free_only is None or self._free_only(model_id)

    @staticmethod
    def _error(status: int, body: bytes, headers: httpx.Headers) -> ProviderError:
        try:
            detail = json.loads(body)["error"]["message"]
        except Exception:
            detail = body.decode("utf-8", "replace")
        detail = _short(str(detail))
        retry_after = None
        ra = headers.get("retry-after", "")
        if ra.isdigit():
            retry_after = int(ra)
        if status in (401, 403):
            return ProviderError("auth", f"The provider rejected the API key ({status}). {detail}")
        if status == 402:
            return ProviderError("quota", f"Free credits exhausted or payment required (402). {detail}")
        if status == 429:
            return ProviderError(
                "rate_limit",
                "Rate limit or free quota reached (429). OMNI did not retry and will not use a paid plan. "
                + (f"Try again in about {retry_after}s." if retry_after else "Try again later."),
                retry_after,
            )
        if status in (400, 404, 422):
            return ProviderError("bad_request", f"The provider rejected the request ({status}). {detail}")
        return ProviderError("unavailable", f"The provider is unavailable ({status}). {detail}")

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with self._client() as client:
                r = await client.get("/models")
        except httpx.TimeoutException:
            raise ProviderError("timeout", "The provider did not respond in time.")
        except httpx.HTTPError:
            raise ProviderError("unavailable", "Could not reach the provider.")
        if r.status_code != 200:
            raise self._error(r.status_code, r.content, r.headers)
        models = []
        for item in r.json().get("data", []):
            mid = item.get("id")
            if not mid or not self._is_allowed(mid):
                continue
            ctx = item.get("context_window") or item.get("context_length")
            models.append(ModelInfo(id=mid, context_window=ctx if isinstance(ctx, int) else None))
        return sorted(models, key=lambda m: m.id)

    async def stream_chat(
        self, messages: list[ChatMessage], model: str, max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        if not self._is_allowed(model):
            raise ProviderError(
                "paid_blocked",
                f"Model '{model}' is not marked free. OMNI blocks it unless OMNI_ALLOW_PAID_PROVIDERS=true.",
            )
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "max_tokens": max_tokens,
        }
        started = False
        for attempt in range(self._max_retries + 1):
            try:
                async with self._client() as client:
                    async with client.stream("POST", "/chat/completions", json=payload) as r:
                        if r.status_code != 200:
                            raise self._error(r.status_code, await r.aread(), r.headers)
                        async for line in r.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if data == "[DONE]":
                                return
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            usage = None
                            u = chunk.get("usage")
                            if isinstance(u, dict):
                                usage = TokenUsage(u.get("prompt_tokens"), u.get("completion_tokens"))
                            choices = chunk.get("choices") or []
                            text = (choices[0].get("delta") or {}).get("content") if choices else None
                            if text or usage:
                                started = started or bool(text)
                                yield StreamEvent(delta=text or "", usage=usage)
                        return
            except ProviderError as e:
                if e.kind == "unavailable" and not started and attempt < self._max_retries:
                    await asyncio.sleep(self._backoff * 2**attempt)
                    continue
                raise
            except httpx.TimeoutException:
                if not started and attempt < self._max_retries:
                    await asyncio.sleep(self._backoff * 2**attempt)
                    continue
                raise ProviderError("timeout", "The provider did not respond in time.")
            except httpx.HTTPError:
                if not started and attempt < self._max_retries:
                    await asyncio.sleep(self._backoff * 2**attempt)
                    continue
                raise ProviderError("unavailable", "Could not reach the provider.")
