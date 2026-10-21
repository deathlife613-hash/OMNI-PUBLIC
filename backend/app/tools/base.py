"""Tool framework. Tools are explicitly registered with a Pydantic input schema, a timeout and a
confirmation flag. The model never gets arbitrary shell, network or filesystem access through here."""
import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel


class ToolError(Exception):
    """A user-presentable failure (bad input, not allowed, disabled...)."""


@dataclass(frozen=True)
class ToolContext:
    db_path: Any
    docs_dir: Any
    now: Callable[[], Any]
    services: Any = None  # optional server-side clients (e.g. n8n); never exposed to callers


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], Any]
    needs_confirmation: bool = False  # destructive / consequential
    timeout_s: float = 5.0
    is_async: bool = False  # network tools: handler is a coroutine function and enforces its own timeout

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "needs_confirmation": self.needs_confirmation,
        }


async def run_with_timeout(tool: Tool, ctx: ToolContext, args: BaseModel, timeout_s: float) -> Any:
    if tool.is_async:  # the handler owns the network timeout; this is only an outer safety net
        return await asyncio.wait_for(tool.handler(ctx, args), timeout=tool.timeout_s)
    return await asyncio.wait_for(asyncio.to_thread(tool.handler, ctx, args), timeout=min(timeout_s, tool.timeout_s))
