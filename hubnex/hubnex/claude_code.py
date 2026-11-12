"""Personal Claude Code CLI bridge. Claude Code owns its login and credentials."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

from hubnex.providers import ProviderError, to_openai_messages


class BridgeUnavailable(ProviderError):
    """The local CLI or its own sign-in is unavailable (eligible for explicit fallback)."""


REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "tool_calls": {"type": "array", "items": {
            "type": "object", "properties": {
                "name": {"type": "string"},
                "input": {"type": "object"},
            }, "required": ["name", "input"],
        }},
    },
    "required": ["text", "tool_calls"],
}


def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    # The CLI must use the owner's own login, never silently select the API key.
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                 "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
        env.pop(name, None)
    env.setdefault("CLAUDE_CONFIG_DIR", "/data/claude-code")
    return env


async def auth_status() -> dict:
    binary = shutil.which("claude")
    if not binary:
        return {"status": "unavailable", "detail": "Claude Code non installato"}
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(binary, "auth", "status", stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE, env=cli_env())
        out, _ = await asyncio.wait_for(proc.communicate(), 15)
        data = json.loads(out)
        if not isinstance(data, dict):
            raise ValueError("invalid status")
    except (OSError, ValueError, asyncio.TimeoutError):
        if proc and proc.returncode is None:
            proc.kill()
            await proc.wait()
        return {"status": "unavailable", "detail": "Stato di Claude Code non disponibile"}
    if proc.returncode:
        return {"status": "signed_out", "detail": "Accedi con claude auth login"}
    if data.get("authMethod") != "claude.ai":
        return {"status": "wrong_account", "detail": "Claude Code non usa l'abbonamento Claude"}
    return {"status": "ready", "detail": "Accesso Claude confermato"}


def _render_messages(messages: list, directory: Path) -> tuple[str, bool]:
    result = []
    attachment = 0
    for message in to_openai_messages(None, messages):
        parts = message.get("content")
        if isinstance(parts, list):
            rendered = []
            for part in parts:
                if part["type"] == "image_url":
                    attachment += 1
                    url = part["image_url"]["url"]
                    media, data = url.split(",", 1)
                    suffix = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(
                        media.partition(";")[0][5:], ".jpg")
                    path = directory / f"attachment-{attachment}{suffix}"
                    path.write_bytes(base64.b64decode(data))
                    rendered.append(f"Immagine allegata: {path} (usa Read per guardarla)")
                else:
                    rendered.append(part.get("text", ""))
            content = "\n".join(rendered)
        else:
            content = parts or ""
        if message.get("tool_calls"):
            content += "\nTool richiesti: " + json.dumps(message["tool_calls"], ensure_ascii=False)
        result.append(f"{message['role'].upper()}: {content}")
    return "\n\n".join(result), attachment > 0


def _response(data: dict) -> NS:
    answer = data.get("structured_output")
    if answer is None:
        try:
            answer = json.loads(data.get("result") or "")
        except ValueError as exc:
            raise ProviderError("Claude Code non ha restituito una risposta strutturata") from exc
    if not isinstance(answer, dict) or not isinstance(answer.get("text"), str) or not isinstance(answer.get("tool_calls"), list):
        raise ProviderError("Risposta Claude Code incompleta")
    blocks = [NS(type="text", text=answer["text"])] if answer["text"] else []
    for i, call in enumerate(answer["tool_calls"]):
        if not isinstance(call, dict) or not isinstance(call.get("name"), str) or not isinstance(call.get("input"), dict):
            raise ProviderError("Richiesta di strumento Claude Code non valida")
        blocks.append(NS(type="tool_use", id=f"cli_{i}", name=call["name"], input=call["input"]))
    u = data.get("usage") or {}
    usage = NS(input_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0),
               cache_read_input_tokens=u.get("cache_read_input_tokens", 0),
               cache_creation_input_tokens=u.get("cache_creation_input_tokens", 0),
               subscription=True)
    return NS(content=blocks, stop_reason="tool_use" if answer["tool_calls"] else "end_turn", usage=usage)


class ClaudeStream:
    """Surface CLI progress as the Anthropic events used by HubNEX's agent loop."""

    def __init__(self, runner, kwargs: dict):
        self.runner, self.kwargs = runner, kwargs
        self.events: asyncio.Queue = asyncio.Queue()
        self.task = None

    async def __aenter__(self):
        async def on_event(kind: str, name: str = ""):
            await self.events.put(NS(type="content_block_start", content_block=NS(type=kind, name=name)))

        async def run():
            try:
                return await self.runner(self.kwargs, on_event=on_event)
            finally:
                await self.events.put(None)

        self.task = asyncio.create_task(run())
        return self

    async def __aexit__(self, *exc):
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        return False

    def __aiter__(self):
        async def events():
            while (event := await self.events.get()) is not None:
                yield event
        return events()

    async def get_final_message(self):
        return await self.task


async def call(model: str, kwargs: dict, on_event=None) -> NS:
    # ponytail: one CLI run per HubNEX tool turn; a persistent MCP session would reduce latency.
    binary = shutil.which("claude")
    if not binary:
        raise BridgeUnavailable("Claude Code non installato")
    status = await auth_status()
    if status["status"] != "ready":
        raise BridgeUnavailable(status["detail"])
    with tempfile.TemporaryDirectory(prefix="hubnex-claude-") as temp:
        directory = Path(temp)
        prompt, has_attachment = _render_messages(kwargs.get("messages") or [], directory)
        system_file = directory / "agent-system.txt"
        system_file.write_text(kwargs.get("system") or "", encoding="utf-8")
        tools = [t for t in kwargs.get("tools") or [] if "input_schema" in t]
        hosted = {t.get("name") for t in kwargs.get("tools") or [] if "input_schema" not in t}
        if tools:
            prompt += "\n\nSTRUMENTI HUBNEX DISPONIBILI:\n" + json.dumps(tools, ensure_ascii=False)
        required_format = (kwargs.get("output_config") or {}).get("format") or {}
        if required_format.get("type") == "json_schema":
            prompt += "\n\nIl testo finale deve essere JSON valido per questo schema: " + json.dumps(required_format["schema"])
        prompt += ("\n\nRispondi con text e tool_calls secondo lo schema. Se serve uno strumento HubNEX, "
                   "richiedilo in tool_calls e attendi il risultato; non inventare il risultato. "
                   "Non usare altri strumenti o file, salvo Read per gli allegati qui sopra.")
        builtins = ["Read"] if has_attachment else []
        if "web_search" in hosted:
            builtins.append("WebSearch")
        if "web_fetch" in hosted:
            builtins.append("WebFetch")
        args = [binary, "--bare", "-p", "Completa la richiesta ricevuta su stdin.", "--output-format",
                "stream-json" if on_event else "json",
                "--json-schema", json.dumps(REPLY_SCHEMA), "--model", model,
                "--tools", ",".join(builtins), "--permission-mode", "dontAsk",
                "--append-system-prompt-file", str(system_file), "--no-session-persistence"]
        if on_event:
            args.extend(["--verbose", "--include-partial-messages"])
        if builtins:
            args.extend(["--allowedTools", *builtins])
        try:
            proc = await asyncio.create_subprocess_exec(*args, cwd=directory, env=cli_env(),
                                                        stdin=asyncio.subprocess.PIPE,
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            if on_event:
                async def stream_reply():
                    proc.stdin.write(prompt.encode())
                    await proc.stdin.drain()
                    proc.stdin.close()
                    errors = asyncio.create_task(proc.stderr.read())
                    final = None
                    async for line in proc.stdout:
                        try:
                            item = json.loads(line)
                        except ValueError:
                            continue
                        if item.get("type") == "stream_event":
                            event = item.get("event") or {}
                            if event.get("type") == "content_block_start":
                                block = event.get("content_block") or {}
                                if block.get("type") in {"text", "tool_use", "server_tool_use"}:
                                    await on_event(block["type"], block.get("name", ""))
                        elif item.get("type") == "result":
                            final = item
                    await proc.wait()
                    return json.dumps(final or {}).encode(), await errors

                out, err = await asyncio.wait_for(stream_reply(), 300)
            else:
                out, err = await asyncio.wait_for(proc.communicate(prompt.encode()), 300)
        except asyncio.CancelledError:
            if "proc" in locals() and proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        except (OSError, asyncio.TimeoutError) as exc:
            if "proc" in locals() and proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise BridgeUnavailable(f"Claude Code non raggiungibile: {exc}") from exc
    if proc.returncode:
        detail = err.decode(errors="replace")[-400:] or out.decode(errors="replace")[-400:]
        if any(word in detail.lower() for word in ("login", "auth", "credential", "not found")):
            raise BridgeUnavailable("Accesso Claude Code scaduto o non disponibile")
        raise ProviderError(f"Claude Code: {detail}")
    try:
        data = json.loads(out)
    except ValueError as exc:
        raise ProviderError("Claude Code non ha restituito JSON valido") from exc
    if data.get("is_error"):
        raise ProviderError(f"Claude Code: {str(data.get('result', 'errore'))[:400]}")
    return _response(data)
