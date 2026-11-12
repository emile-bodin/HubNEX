"""Other AI providers: OpenAI and anything that speaks its API (Ollama, LM Studio, OpenRouter…).

A model name with a prefix goes to that provider: `openai:gpt-5-mini`, `ollama:qwen3:14b`,
`compat:some-model` (any OpenAI-compatible server). Without a prefix it is Claude, as before.

The rest of HubNEX talks to Claude's Messages API. `ProviderRouter` keeps that shape: it passes
Claude models to Anthropic and translates the others to and from OpenAI's chat completions, so
the agent loop, tools, memory and history work unchanged. What only Claude has (web search run
by Anthropic, visible thinking, prompt caching) is simply not there with the others.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from types import SimpleNamespace as NS
from typing import Any

import httpx

log = logging.getLogger("hubnex.providers")

PREFIXES = ("openai", "ollama", "compat")
OPENAI_URL = "https://api.openai.com/v1"


def split_model(model: str) -> tuple[str, str]:
    """('anthropic', model) for Claude, else (provider, the provider's own model name)."""
    head, sep, rest = (model or "").partition(":")
    if sep and head.lower() in PREFIXES and rest:
        return head.lower(), rest
    return "anthropic", model


def is_claude(model: str) -> bool:
    return split_model(model)[0] == "anthropic"


@dataclass
class Endpoint:
    url: str  # base URL, up to /v1
    key: str = ""


def endpoints(settings) -> dict[str, Endpoint]:
    ollama = (settings.ollama_url or "").rstrip("/")
    if ollama and not ollama.endswith("/v1"):
        ollama += "/v1"  # Ollama's OpenAI-compatible API
    return {
        "openai": Endpoint((settings.openai_base_url or OPENAI_URL).rstrip("/"), settings.openai_api_key),
        "ollama": Endpoint(ollama),
        "compat": Endpoint((settings.compat_base_url or "").rstrip("/"), settings.compat_api_key),
    }


# ---------------------------------------------------------------------- Claude -> OpenAI
def _get(block, key, default=None):
    return block.get(key, default) if isinstance(block, dict) else getattr(block, key, default)


def pdf_text(data: bytes, limit: int = 60_000) -> str:
    """The text of a PDF: other models don't read PDFs, so they get what it says."""
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(data)
        pages = []
        for i in range(len(doc)):
            pages.append(doc[i].get_textpage().get_text_range())
            if sum(map(len, pages)) > limit:
                break
        return "\n\n".join(pages)[:limit].strip() or "[PDF senza testo: probabilmente una scansione]"
    except Exception as exc:  # a broken PDF must not break the conversation
        return f"[PDF illeggibile: {exc}]"


def _parts(content) -> tuple[list[dict], list[dict]]:
    """Claude content blocks -> OpenAI parts (text, image_url) and the tool results among them."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}], []
    parts, results = [], []
    for b in content or []:
        kind = _get(b, "type")
        if kind == "text":
            parts.append({"type": "text", "text": _get(b, "text", "")})
        elif kind == "image":
            src = _get(b, "source", {}) or {}
            parts.append({"type": "image_url", "image_url": {"url": f"data:{src.get('media_type', 'image/jpeg')};base64,{src.get('data', '')}"}})
        elif kind == "document":
            src = _get(b, "source", {}) or {}
            title = _get(b, "title") or "documento"
            if src.get("type") == "base64" and src.get("media_type") == "application/pdf":
                text = pdf_text(base64.b64decode(src.get("data", "")))
            else:
                text = src.get("data", "")
            parts.append({"type": "text", "text": f"«{title}»:\n{text}"})
        elif kind == "tool_result":
            results.append(b)
    return parts, results


def _flat(parts: list[dict]) -> str | list[dict]:
    """Plain text when there are no images (some local servers accept only strings)."""
    if all(p["type"] == "text" for p in parts):
        return "\n\n".join(p["text"] for p in parts)
    return parts


def to_openai_messages(system, messages: list[dict]) -> list[dict]:
    if isinstance(system, list):
        system = "\n\n".join(_get(b, "text", "") for b in system)
    out: list[dict] = [{"role": "system", "content": system}] if system else []
    for m in messages:
        role, content = m["role"], m["content"]
        if role == "assistant":
            texts, calls = [], []
            for b in content if isinstance(content, list) else [{"type": "text", "text": content}]:
                kind = _get(b, "type")
                if kind == "text" and _get(b, "text"):
                    texts.append(_get(b, "text"))
                elif kind == "tool_use":
                    calls.append({"id": _get(b, "id"), "type": "function",
                                  "function": {"name": _get(b, "name"), "arguments": json.dumps(_get(b, "input") or {}, ensure_ascii=False)}})
            msg: dict[str, Any] = {"role": "assistant", "content": "\n\n".join(texts) or (None if calls else "")}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        parts, results = _parts(content)
        images: list[dict] = []
        for r in results:  # each tool result is its own message, right after the call
            rparts, _ = _parts(_get(r, "content", ""))
            images += [p for p in rparts if p["type"] == "image_url"]
            text = "\n\n".join(p["text"] for p in rparts if p["type"] == "text")
            if _get(r, "is_error"):
                text = f"Errore: {text}"
            out.append({"role": "tool", "tool_call_id": _get(r, "tool_use_id"), "content": text or "(vuoto)"})
        if images:  # tools can't return pictures here: they follow as the user's
            parts = [{"type": "text", "text": "Le immagini restituite dallo strumento:"}, *images, *parts]
        if parts:
            out.append({"role": "user", "content": _flat(parts)})
    return out


def to_openai_tools(tools: list[dict] | None) -> list[dict]:
    out = []
    for t in tools or []:
        if "input_schema" not in t:  # Anthropic's own tools (web search…): not here
            continue
        out.append({"type": "function", "function": {
            "name": t["name"], "description": t.get("description", "")[:1024], "parameters": t["input_schema"]}})
    return out


REASONING = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}


def request_body(provider: str, model: str, kwargs: dict) -> dict:
    body: dict[str, Any] = {"model": model, "messages": to_openai_messages(kwargs.get("system"), kwargs.get("messages") or [])}
    tools = to_openai_tools(kwargs.get("tools"))
    if tools:
        body["tools"] = tools
    out = kwargs.get("output_config") or {}
    fmt = out.get("format")
    if fmt and fmt.get("type") == "json_schema":
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "risposta", "schema": fmt["schema"]}}
    # Effort only where it exists: OpenAI's reasoning models.
    if provider == "openai" and out.get("effort") and model.startswith(("o", "gpt-5")):
        body["reasoning_effort"] = REASONING.get(out["effort"], "medium")
    return body


# ---------------------------------------------------------------------- OpenAI -> Claude
STOP = {"tool_calls": "tool_use", "length": "max_tokens", "content_filter": "refusal"}


def from_openai(data: dict) -> NS:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = []
    if msg.get("content"):
        content.append(NS(type="text", text=msg["content"]))
    for i, call in enumerate(msg.get("tool_calls") or []):
        fn = call.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        content.append(NS(type="tool_use", id=call.get("id") or f"call_{i}", name=fn.get("name", ""), input=args if isinstance(args, dict) else {}))
    stop = STOP.get(choice.get("finish_reason"), "end_turn")
    if any(b.type == "tool_use" for b in content):
        stop = "tool_use"  # some local servers say "stop" even when they call a tool
    u = data.get("usage") or {}
    cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    usage = NS(input_tokens=max(0, (u.get("prompt_tokens") or 0) - cached), output_tokens=u.get("completion_tokens") or 0,
               cache_read_input_tokens=cached, cache_creation_input_tokens=0, server_tool_use=None)
    return NS(content=content, stop_reason=stop, usage=usage)


class ProviderError(RuntimeError):
    pass


class _Done:
    """The stream the agent loop expects, from a reply that came all at once."""

    def __init__(self, coro):
        self._coro = coro
        self._resp = None

    async def __aenter__(self):
        self._resp = await self._coro
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for block in self._resp.content:
                yield NS(type="content_block_start", content_block=block)

        return gen()

    async def get_final_message(self):
        return self._resp


class ProviderRouter:
    """Looks like the Anthropic client; sends each request to the model's own provider."""

    def __init__(self, anthropic_client, settings, http: httpx.AsyncClient | None = None):
        self.anthropic = anthropic_client
        self.settings = settings
        self._http = http
        self.claude_error = ""
        self.beta = NS(messages=NS(stream=self._stream, create=self._create))

    _OWN = {"anthropic", "settings", "_http", "beta", "claude_error"}

    async def _claude_call(self, kwargs: dict, on_event=None):
        mode = self.settings.claude_auth_mode
        if mode == "api_key":
            return await self.anthropic.beta.messages.create(**kwargs)
        if not self.settings.claude_subscription_enabled:
            raise ProviderError("Attiva Claude subscription nelle opzioni dell'add-on")
        from hubnex.claude_code import BridgeUnavailable, call

        try:
            reply = await call(kwargs["model"], kwargs, on_event=on_event)
            self.claude_error = ""
            return reply
        except BridgeUnavailable as exc:
            self.claude_error = str(exc)
            if mode == "hybrid" and self.settings.claude_api_fallback and os.environ.get("ANTHROPIC_API_KEY"):
                return await self.anthropic.beta.messages.create(**kwargs)
            raise
        except ProviderError as exc:
            self.claude_error = str(exc)
            raise

    def __getattr__(self, name):  # anything else is the Anthropic client's (and the tests' fakes')
        return getattr(self.anthropic, name)

    def __setattr__(self, name, value):
        if name in self._OWN:
            object.__setattr__(self, name, value)
        else:
            setattr(self.anthropic, name, value)

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10))  # local models can be slow
        return self._http

    async def _call(self, provider: str, model: str, kwargs: dict) -> NS:
        ep = endpoints(self.settings)[provider]
        if not ep.url:
            raise ProviderError(f"{provider}: manca l'indirizzo del server nelle opzioni dell'add-on")
        if provider == "openai" and not ep.key:
            raise ProviderError("openai: manca la chiave API nelle opzioni dell'add-on")
        headers = {"Authorization": f"Bearer {ep.key}"} if ep.key else {}
        try:
            r = await self._client().post(f"{ep.url}/chat/completions", json=request_body(provider, model, kwargs), headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderError(f"{provider} non raggiungibile ({ep.url}): {exc}") from exc
        if r.status_code >= 400:
            try:
                detail = (r.json().get("error") or {}).get("message") or r.text
            except ValueError:
                detail = r.text
            raise ProviderError(f"{provider} {r.status_code}: {str(detail)[:300]}")
        return from_openai(r.json())

    def _stream(self, **kwargs):
        provider, model = split_model(kwargs.get("model", ""))
        if provider == "anthropic":
            if self.settings.claude_auth_mode == "api_key":
                return self.anthropic.beta.messages.stream(**kwargs)
            from hubnex.claude_code import ClaudeStream

            if not self.settings.claude_subscription_enabled:
                return _Done(self._claude_call(kwargs))
            return ClaudeStream(self._claude_call, kwargs)
        return _Done(self._call(provider, model, kwargs))

    async def _create(self, **kwargs):
        provider, model = split_model(kwargs.get("model", ""))
        if provider == "anthropic":
            return await self._claude_call(kwargs)
        return await self._call(provider, model, kwargs)
