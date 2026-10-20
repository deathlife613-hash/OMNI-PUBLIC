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


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[ToolContext, Any], Any]
    needs_confirmation: bool = False  # destructive / consequential
    timeout_s: float = 5.0

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "needs_confirmation": self.needs_confirmation,
        }


async def run_with_timeout(tool: Tool, ctx: ToolContext, args: BaseModel, timeout_s: float) -> Any:
    return await asyncio.wait_for(asyncio.to_thread(tool.handler, ctx, args), timeout=min(timeout_s, tool.timeout_s))
