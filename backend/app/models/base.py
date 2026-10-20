"""Provider-independent interface. OMNI core only ever talks to these types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class ModelInfo:
    id: str
    context_window: int | None = None  # None = provider did not report it


@dataclass
class TokenUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class StreamEvent:
    delta: str = ""
    usage: TokenUsage | None = None


class ProviderError(Exception):
    """kind: not_configured | no_model | auth | rate_limit | quota | timeout |
    unavailable | bad_request | paid_blocked | unsupported"""

    def __init__(self, kind: str, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_after = retry_after


class Provider(ABC):
    name: str

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Cheap call that validates credentials without spending chat quota."""

    @abstractmethod
    def stream_chat(
        self, messages: list[ChatMessage], model: str, max_tokens: int
    ) -> AsyncIterator[StreamEvent]:
        """Yield text deltas. Raise ProviderError on failure."""
