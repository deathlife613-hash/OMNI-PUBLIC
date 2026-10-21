"""Optional server-side TTS. Absent configuration changes nothing elsewhere in OMNI."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.security.auth import require_auth
from app.services.tts import TTSError, tts_state

router = APIRouter(dependencies=[Depends(require_auth)])


class SpeakBody(BaseModel):
    text: str


def _err(e: TTSError) -> HTTPException:
    return HTTPException(e.status, {"kind": e.kind, "message": e.message})


@router.get("/voice/status")
def voice_status(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    return tts_state(settings, request.app.state.tts_guard, request.app.state.tts is not None)


@router.post("/voice/speak")
async def speak(body: SpeakBody, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    tts, guard = request.app.state.tts, request.app.state.tts_guard
    if tts is None:
        raise _err(TTSError("not_configured", "Server voice is not configured. Using browser voices.", 503))
    text = body.text.strip()
    if not text:
        raise _err(TTSError("empty", "Nothing to speak.", 422))
    if len(text) > settings.tts_max_chars_per_reply:
        raise _err(TTSError("too_long", f"Reply is {len(text)} characters; the limit is {settings.tts_max_chars_per_reply} (protects the free allowance). Use the browser voice for long replies.", 413))
    key = guard.key(tts.voice_id, tts.model, text)
    audio = guard.get(key)
    cached = audio is not None
    if audio is None:
        if guard.chars_used + len(text) > settings.tts_monthly_char_cap:
            raise _err(TTSError("monthly_cap", f"OMNI's own monthly voice limit ({settings.tts_monthly_char_cap} characters, an estimate) would be exceeded. Use the browser voice.", 429))
        pending = guard.inflight.get(key)
        if pending is not None:  # a duplicate click/effect while the same text is generating: share that one request
            try:
                audio = await asyncio.shield(pending)
            except TTSError as e:
                raise _err(e) from None
            cached = True
        else:
            fut = asyncio.get_running_loop().create_future()
            guard.inflight[key] = fut
            try:
                audio = await tts.synthesize(text)
            except TTSError as e:
                fut.set_exception(e)
                fut.exception()  # mark retrieved so asyncio does not log it when nobody awaits
                raise _err(e) from None
            finally:
                guard.inflight.pop(key, None)
            fut.set_result(audio)
            guard.add_chars(len(text))  # charged only after a successful generation
            guard.generations += 1
            guard.put(key, audio)
    return Response(audio, media_type="audio/mpeg", headers={"X-OMNI-TTS-Cache": "hit" if cached else "miss"})
