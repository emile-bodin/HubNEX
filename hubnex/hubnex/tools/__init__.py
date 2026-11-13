"""Tools the agents can use. Each agent gets the subset listed in agents.yaml."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from hubnex.hq import HQ


@dataclass
class ToolContext:
    hq: "HQ"
    agent_id: str
    company: str | None  # None for Jarvis (works across companies)


Handler = Callable[[ToolContext, dict], Awaitable[Any]]


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    handler: Handler

    def definition(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.schema}


# Anthropic-hosted tools: declared by type, executed server-side. The dynamic-filtering
# versions need Sonnet/Opus; Haiku gets the basic ones.
SERVER_TOOLS: dict[str, tuple[str, str]] = {
    "web_search": ("web_search_20260209", "web_search_20250305"),
    "web_fetch": ("web_fetch_20260209", "web_fetch_20250910"),
}


def server_tool(name: str, model: str, max_uses: int = 5) -> dict:
    current, basic = SERVER_TOOLS[name]
    return {"type": basic if "haiku" in model else current, "name": name, "max_uses": max_uses}

REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict, required: list[str] | None = None):
    def wrap(fn: Handler) -> Handler:
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            schema={"type": "object", "properties": properties, "required": required or []},
            handler=fn,
        )
        return fn

    return wrap


def to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


# Import the modules that register tools.
from hubnex.tools import boss, common, ha_history, homeassistant, mail, web  # noqa: E402,F401

__all__ = ["REGISTRY", "SERVER_TOOLS", "Tool", "ToolContext", "server_tool", "to_text"]
