"""The agent loop: Claude + tools, streaming so the HQ can show what each agent is doing."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

import anthropic

log = logging.getLogger("hubnex.llm")

# Server-side fallback: if a safety classifier declines, the API re-runs the request on a
# suitable model instead of returning a refusal. Haiku has no server-side fallback.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


def fallback_args(model: str) -> dict:
    if model in FALLBACK_MODELS:
        return {"betas": [FALLBACK_BETA], "fallbacks": "default"}
    return {}


def text_of(response) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text").strip()


async def complete(
    client: anthropic.AsyncAnthropic,
    *,
    model: str,
    system: str,
    prompt: str | list,  # text, or content blocks (e.g. an image and a question)
    effort: str = "low",
    schema: dict | None = None,
    max_tokens: int = 8000,
    on_usage: UsageCallback | None = None,
) -> str:
    """A single request without tools. With `schema`, the reply is guaranteed JSON."""
    kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort},
        **fallback_args(model),
    )
    if schema:
        kwargs["output_config"]["format"] = {"type": "json_schema", "schema": schema}
    response = await client.beta.messages.create(**kwargs)
    if on_usage:
        await on_usage(response.usage, model)
    if response.stop_reason == "refusal":
        raise RuntimeError("richiesta rifiutata dal modello")
    return text_of(response)

class RunGate:
    """At most `slots` model calls at once, and work nobody is waiting for (routines, events,
    mail) may hold at most `slots - 1` of them: a person never waits behind the house's
    scheduled work. The gate is around each model call, not a whole task, so Jarvis waiting
    for an agent he delegated to never holds a seat the agent needs."""

    def __init__(self, slots: int = 3):
        self.slots = max(1, int(slots))
        self.busy = 0
        self.unattended = 0
        self._cond = asyncio.Condition()

    def _free(self, person: bool) -> bool:
        if self.busy >= self.slots:
            return False
        return person or self.slots == 1 or self.unattended < self.slots - 1

    @asynccontextmanager
    async def seat(self, person: bool = True) -> AsyncIterator[None]:
        async with self._cond:
            await self._cond.wait_for(lambda: self._free(person))
            self.busy += 1
            self.unattended += 0 if person else 1
        try:
            yield
        finally:
            async with self._cond:
                self.busy -= 1
                self.unattended -= 0 if person else 1
                self._cond.notify_all()


StatusCallback = Callable[[str, str | None], Awaitable[None]]  # (status, detail)
DeltaCallback = Callable[[str], Awaitable[None]]  # a piece of the answer as it is written
ToolExecutor = Callable[[str, dict], Awaitable[tuple[str | list, bool]]]  # (name, input) -> (text or content blocks, is_error)
UsageCallback = Callable[[Any, str], Awaitable[None]]  # (usage, model): for the credit counter


@dataclass
class LoopResult:
    text: str
    stop_reason: str
    turns: int


async def run_agent_loop(
    client: anthropic.AsyncAnthropic,
    *,
    model: str,
    effort: str,
    system: str,
    tools: list[dict],
    messages: list[dict],
    execute: ToolExecutor,
    on_status: StatusCallback,
    on_usage: UsageCallback | None = None,
    max_turns: int = 30,
    on_delta: DeltaCallback | None = None,
    seat: Callable[[], Any] | None = None,
) -> LoopResult:
    """Run Claude until it stops calling tools. `messages` is appended to in place.

    History is append-only (assistant content goes back exactly as returned), which keeps
    thinking blocks valid and the prompt cache warm across turns.
    """
    turns = 0
    while True:
        turns += 1
        if turns > max_turns:
            return LoopResult("Mi fermo: troppi passaggi per questo compito.", "max_turns", turns)

        await on_status("thinking", None)
        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=32000,
            system=system,
            messages=messages,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": effort},
            cache_control={"type": "ephemeral"},
            **fallback_args(model),
        )
        if tools:
            kwargs["tools"] = tools

        async with (seat() if seat else nullcontext()):
            async with client.beta.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if on_delta and getattr(delta, "type", None) == "text_delta" and delta.text:
                            await on_delta(delta.text)
                        continue
                    if event.type != "content_block_start":
                        continue
                    block_type = event.content_block.type
                    if block_type == "text":
                        await on_status("writing", None)
                    elif block_type == "tool_use":
                        await on_status("working", event.content_block.name)
                    elif block_type == "server_tool_use":
                        await on_status("searching", event.content_block.name)
                response = await stream.get_final_message()
        if on_usage:
            await on_usage(response.usage, model)

        for block in response.content:
            if block.type == "thinking" and block.thinking:
                await on_status("thought", block.thinking)

        messages.append({"role": "assistant", "content": response.content})
        text = text_of(response)

        if response.stop_reason == "refusal":
            return LoopResult(text or "Non posso aiutarti con questa richiesta.", "refusal", turns)
        if response.stop_reason == "pause_turn":
            # A server tool (web search) hit its iteration limit: re-send to let it continue.
            continue
        if response.stop_reason == "max_tokens":
            return LoopResult((text + "\n\n[risposta troncata]").strip(), "max_tokens", turns)
        if response.stop_reason != "tool_use":
            return LoopResult(text, response.stop_reason or "end_turn", turns)

        calls = [b for b in response.content if b.type == "tool_use"]

        async def run_one(call) -> dict:
            await on_status("working", call.name)
            try:
                result, is_error = await execute(call.name, call.input if isinstance(call.input, dict) else {})
            except Exception as exc:  # tool failures go back to Claude, not up the stack
                log.exception("tool %s failed", call.name)
                result, is_error = f"Errore: {exc}", True
            block = {"type": "tool_result", "tool_use_id": call.id, "content": result}
            if is_error:
                block["is_error"] = True
            return block

        # All results go back in a single user message.
        results = await asyncio.gather(*(run_one(c) for c in calls))
        messages.append({"role": "user", "content": list(results)})
