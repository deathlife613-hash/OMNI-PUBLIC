"""Server-side text-to-speech (ElevenLabs first). Optional: with no provider configured OMNI uses the
browser's own voices and nothing here runs. The API key lives only in server env and is never logged,
returned, or put in an error message."""
from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict

import httpx

from app.core.config import Settings


class TTSError(Exception):
    """kind: not_configured | too_long | empty | monthly_cap | auth | payment | rate_limit | bad_request | timeout | unreachable | provider_error | bad_audio"""

    def __init__(self, kind: str, message: str, status: int = 502):
        super().__init__(message)
        self.kind, self.message, self.status = kind, message, status


class TTSGuard:
    """In-memory cache (identical text is never generated twice) and a monthly character counter.

    The counter is OMNI's own ESTIMATE of characters sent this calendar month (UTC). It resets on restart
    and is not the provider's real balance, so it is labelled as an estimate everywhere it is shown."""

    def __init__(self, max_entries: int = 64):
        self.max_entries = max(1, max_entries)
        self.cache: OrderedDict[str, bytes] = OrderedDict()
        self.cache_hits = 0
        self.generations = 0
        self.inflight: dict[str, asyncio.Future] = {}  # identical concurrent requests share one billable call
        self._month = ""
        self._chars = 0

    @staticmethod
    def key(voice: str, model: str, text: str) -> str:
        return hashlib.sha256(f"{voice}\x00{model}\x00{text}".encode()).hexdigest()

    def _roll(self) -> None:
        month = time.strftime("%Y-%m", time.gmtime())
        if month != self._month:
            self._month, self._chars = month, 0

    @property
    def chars_used(self) -> int:
        self._roll()
        return self._chars

    def add_chars(self, n: int) -> None:
        self._roll()
        self._chars += n

    def get(self, key: str) -> bytes | None:
        audio = self.cache.get(key)
        if audio is not None:
            self.cache.move_to_end(key)
            self.cache_hits += 1
        return audio

    def put(self, key: str, audio: bytes) -> None:
        self.cache[key] = audio
        self.cache.move_to_end(key)
        while len(self.cache) > self.max_entries:
            self.cache.popitem(last=False)


class ElevenLabsTTS:
    name = "elevenlabs"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._key = settings.tts_api_key
        self.voice_id = settings.tts_voice_id
        self.model = settings.tts_model
        self._base = settings.tts_base_url.rstrip("/")
        self._timeout = settings.tts_timeout_s
        self._transport = transport
        self._slots = asyncio.Semaphore(2)  # free plan allows 2 concurrent requests

    async def synthesize(self, text: str) -> bytes:
        """One call = at most one billable request. There is deliberately NO automatic retry: after a timeout
        the first request may have succeeded and been billed, so retrying could double-spend."""
        url = f"{self._base}/v1/text-to-speech/{self.voice_id}"
        try:
            async with self._slots, httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as c:
                r = await c.post(
                    url,
                    headers={"xi-api-key": self._key, "Accept": "audio/mpeg"},
                    params={"output_format": "mp3_44100_128"},
                    json={"text": text, "model_id": self.model},
                )
        except httpx.TimeoutException:
            raise TTSError("timeout", "The voice service timed out.", 504) from None
        except httpx.HTTPError:
            raise TTSError("unreachable", "Could not reach the voice service.", 502) from None
        if r.status_code in (401, 403):
            raise TTSError("auth", "The voice service rejected the API key (or the free plan has no API access).", 502)
        if r.status_code == 402:
            # 402 = "payment required". Its exact cause on the free plan is unobserved, so do not claim "quota exhausted".
            raise TTSError("payment", "The voice service answered 402 (payment/plan required). The plan may not include this, or its allowance may be used up; the exact cause is not known. Use the browser voice instead.", 402)
        if r.status_code == 429:
            raise TTSError("rate_limit", "The voice service is rate limited. Try again shortly.", 429)
        if r.status_code in (400, 404, 422):
            raise TTSError("bad_request", "The voice service rejected the request. Check OMNI_TTS_VOICE_ID and OMNI_TTS_MODEL.", 502)
        if r.status_code >= 400:
            raise TTSError("provider_error", f"The voice service returned an error ({r.status_code}).", 502)
        if not r.headers.get("content-type", "").lower().startswith("audio/") or not r.content:
            raise TTSError("bad_audio", "The voice service did not return audio. Nothing was played or charged.", 502)  # never treat a body as audio unless it is
        return r.content


def build_tts(settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
    """None when TTS is off or incompletely configured (status reports which)."""
    if settings.tts_provider.lower() == "elevenlabs" and settings.tts_api_key and settings.tts_voice_id:
        return ElevenLabsTTS(settings, transport)
    return None


def tts_state(settings: Settings, guard: TTSGuard, configured: bool) -> dict:
    if not settings.tts_provider:
        reason = "not configured"
    elif settings.tts_provider.lower() != "elevenlabs":
        reason = f"unknown provider '{settings.tts_provider}'"
    elif not settings.tts_api_key:
        reason = "API key missing"
    elif not settings.tts_voice_id:
        reason = "voice id missing"
    else:
        reason = None
    return {
        "configured": configured,
        "provider": settings.tts_provider or None,
        "engine": "elevenlabs" if configured else "browser",
        "note": None if configured else f"TTS: {reason}. Using browser voices.",
        "chars_used_month_estimate": guard.chars_used if configured else None,
        "monthly_char_cap": settings.tts_monthly_char_cap if configured else None,
        "max_chars_per_reply": settings.tts_max_chars_per_reply if configured else None,
        "cache_hits": guard.cache_hits if configured else None,
        "generations": guard.generations if configured else None,
    }
