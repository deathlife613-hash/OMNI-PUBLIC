"""Builds the prompt: persona + as many recent messages as fit the budget.
(Summaries and memory retrieval arrive in Phase 3.)"""
from app.models.base import ChatMessage

SYSTEM_PROMPT = (
    "You are OMNI, a personal AI assistant. Be composed, concise and honest. "
    "Say clearly when you are unsure or lack information. You currently have no tools, "
    "no web access and no memory beyond this conversation; never claim otherwise."
)


def build_context(history: list[ChatMessage], budget_chars: int) -> list[ChatMessage]:
    """`history` is oldest→newest and ends with the new user message (always kept)."""
    kept: list[ChatMessage] = []
    used = len(SYSTEM_PROMPT)
    for msg in reversed(history):
        cost = len(msg.content)
        if kept and used + cost > budget_chars:
            break
        kept.append(msg)
        used += cost
    kept.reverse()
    return [ChatMessage("system", SYSTEM_PROMPT), *kept]
