"""Conversations + streaming chat (Server-Sent Events).

The user's message is saved BEFORE the model is called, so a quota error or
outage never loses it. Non-AI routes (list/create/delete conversations) work
even when no provider is configured.
"""
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.provider import effective_model, resolve_provider
from app.core import db
from app.core.config import Settings, get_settings
from app.models.base import ChatMessage, ProviderError, TokenUsage
from app.security.auth import require_auth
from app.services.context import build_context
from app.services.memory import relevant_memories

router = APIRouter(dependencies=[Depends(require_auth)])
DEFAULT_TITLE = "New conversation"


class NewConversation(BaseModel):
    title: str = Field(default=DEFAULT_TITLE, min_length=1, max_length=120)


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class NewMessage(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


def _row(r) -> dict:
    return dict(r)


def _require_conv(conn, conv_id: str) -> dict:
    r = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if r is None:
        raise HTTPException(404, "Conversation not found.")
    return _row(r)


@router.get("/conversations")
def list_conversations(settings: Settings = Depends(get_settings)) -> list[dict]:
    with db.session(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC, rowid DESC LIMIT 100").fetchall()
    return [_row(r) for r in rows]


@router.post("/conversations", status_code=201)
def create_conversation(body: NewConversation, settings: Settings = Depends(get_settings)) -> dict:
    conv_id = uuid.uuid4().hex
    with db.session(settings.db_path) as conn:
        conn.execute("INSERT INTO conversations(id, title) VALUES (?, ?)", (conv_id, body.title))
        return _require_conv(conn, conv_id)


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str, settings: Settings = Depends(get_settings)) -> dict:
    with db.session(settings.db_path) as conn:
        conv = _require_conv(conn, conv_id)
        msgs = conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
            (conv_id,),
        ).fetchall()
    return {**conv, "messages": [_row(m) for m in msgs]}


@router.patch("/conversations/{conv_id}")
def rename_conversation(conv_id: str, body: Rename, settings: Settings = Depends(get_settings)) -> dict:
    with db.session(settings.db_path) as conn:
        _require_conv(conn, conv_id)
        conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (body.title, conv_id))
        return _require_conv(conn, conv_id)


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, settings: Settings = Depends(get_settings)) -> None:
    with db.session(settings.db_path) as conn:
        _require_conv(conn, conv_id)
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/conversations/{conv_id}/messages")
async def send_message(
    conv_id: str,
    body: NewMessage,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    with db.session(settings.db_path) as conn:
        conv = _require_conv(conn, conv_id)
        conn.execute(
            "INSERT INTO messages(conversation_id, role, content) VALUES (?, 'user', ?)",
            (conv_id, body.content),
        )
        if conv["title"] == DEFAULT_TITLE:
            conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (body.content[:48], conv_id))
        conn.execute(
            "UPDATE conversations SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
            (conv_id,),
        )
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id", (conv_id,)
        ).fetchall()
        mem_on = conn.execute("SELECT value FROM meta WHERE key = 'memory_enabled'").fetchone()
        memories = (
            relevant_memories(conn, body.content) if (mem_on is None or mem_on["value"] == "1") else []
        )
    history = [ChatMessage(r["role"], r["content"]) for r in rows if r["role"] in ("user", "assistant")]
    usage = request.app.state.usage

    async def events():
        started = time.monotonic()
        try:
            provider = resolve_provider(request, settings)
            model = effective_model(settings)
            if not model:
                raise ProviderError("no_model", "No model selected. Pick one in the chat header first.")
        except ProviderError as e:
            usage.record_error(e.kind)
            yield _sse("error", {"kind": e.kind, "message": e.message, "saved_user_message": True})
            return

        parts: list[str] = []
        token_usage: TokenUsage | None = None
        try:
            async for ev in provider.stream_chat(
                build_context(history, settings.context_char_budget, memories), model, settings.ai_max_output_tokens
            ):
                if ev.usage:
                    token_usage = ev.usage
                if ev.delta:
                    parts.append(ev.delta)
                    yield _sse("delta", {"text": ev.delta})
        except ProviderError as e:
            usage.record_error(e.kind)
            yield _sse(
                "error",
                {"kind": e.kind, "message": e.message, "retry_after": e.retry_after, "saved_user_message": True},
            )
            return

        text = "".join(parts)
        if not text:
            usage.record_error("empty_response")
            yield _sse("error", {"kind": "unavailable", "message": "The model returned no text.", "saved_user_message": True})
            return
        with db.session(settings.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO messages(conversation_id, role, content) VALUES (?, 'assistant', ?)",
                (conv_id, text),
            )
            msg_id = cur.lastrowid
            conn.execute(
                "UPDATE conversations SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = ?",
                (conv_id,),
            )
        usage.record_success(
            int((time.monotonic() - started) * 1000),
            token_usage.prompt_tokens if token_usage else None,
            token_usage.completion_tokens if token_usage else None,
        )
        yield _sse("done", {"message_id": msg_id, "model": model})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
