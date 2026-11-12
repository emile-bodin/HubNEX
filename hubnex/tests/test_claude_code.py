"""Offline checks for the personal Claude Code route and explicit API fallback."""

import json
import asyncio
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from hubnex import claude_code, config
from hubnex.providers import ProviderError, ProviderRouter
from hubnex.main import create_app


@pytest.mark.parametrize("mode", ["api_key", "subscription", "hybrid"])
def test_auth_modes(monkeypatch, mode):
    monkeypatch.setattr(config, "_load_addon_options", lambda: False)
    monkeypatch.setattr(config, "_load_dotenv", lambda: None)
    monkeypatch.setenv("HUBNEX_CLAUDE_AUTH_MODE", mode)
    assert config.Settings.from_env().claude_auth_mode == mode


def test_cli_reply_keeps_tool_contract_and_subscription_usage():
    response = claude_code._response({"structured_output": {
        "text": "", "tool_calls": [{"name": "memory_search", "input": {"query": "door"}}]},
        "usage": {"input_tokens": 12, "output_tokens": 4}})
    assert response.stop_reason == "tool_use"
    assert response.content[0].name == "memory_search"
    assert response.usage.subscription and response.usage.input_tokens == 12


async def test_cli_subprocess_returns_a_structured_answer(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: "claude")
    async def ready():
        return {"status": "ready"}
    monkeypatch.setattr(claude_code, "auth_status", ready)
    seen = []

    class Process:
        returncode = 0

        async def communicate(self, prompt):
            seen.append(prompt.decode())
            return json.dumps({"structured_output": {"text": "Ciao", "tool_calls": []},
                               "usage": {"input_tokens": 10, "output_tokens": 2}}).encode(), b""

    async def spawn(*args, **kwargs):
        seen.append(args)
        return Process()

    monkeypatch.setattr(claude_code.asyncio, "create_subprocess_exec", spawn)
    result = await claude_code.call("claude-sonnet-5-5", {"system": "Sei Jarvis", "messages": [
        {"role": "user", "content": "saluta"}]})
    assert result.content[0].text == "Ciao"
    assert "saluta" in seen[1]
    assert "--append-system-prompt-file" in seen[0]
    assert "--safe-mode" in seen[0] and "--bare" not in seen[0]
    assert "ANTHROPIC_API_KEY" not in claude_code.cli_env() or not claude_code.cli_env()["ANTHROPIC_API_KEY"]


async def test_only_unavailable_cli_can_use_explicit_api_fallback(monkeypatch):
    calls = []

    async def api(**kwargs):
        calls.append(kwargs)
        return "api"

    router = ProviderRouter(NS(beta=NS(messages=NS(create=api))), config.Settings(
        claude_auth_mode="hybrid", claude_subscription_enabled=True, claude_api_fallback=True))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    async def unavailable(*args, **kwargs):
        raise claude_code.BridgeUnavailable("login expired")

    monkeypatch.setattr(claude_code, "call", unavailable)
    assert await router._create(model="claude-sonnet-5-5") == "api"
    assert len(calls) == 1

    async def bad_reply(*args, **kwargs):
        raise ProviderError("invalid tool response")

    monkeypatch.setattr(claude_code, "call", bad_reply)
    with pytest.raises(ProviderError, match="invalid tool response"):
        await router._create(model="claude-sonnet-5-5")
    assert len(calls) == 1


async def test_api_mode_and_subscription_without_fallback(monkeypatch):
    calls = []

    async def api(**kwargs):
        calls.append(kwargs)
        return "api"

    client = NS(beta=NS(messages=NS(create=api)))
    router = ProviderRouter(client, config.Settings(claude_auth_mode="api_key"))
    assert await router._create(model="claude-sonnet-5-5") == "api"
    assert len(calls) == 1

    async def unavailable(*args, **kwargs):
        raise claude_code.BridgeUnavailable("signed out")

    monkeypatch.setattr(claude_code, "call", unavailable)
    router = ProviderRouter(client, config.Settings(
        claude_auth_mode="subscription", claude_subscription_enabled=True))
    with pytest.raises(claude_code.BridgeUnavailable, match="signed out"):
        await router._create(model="claude-sonnet-5-5")
    assert len(calls) == 1


@pytest.mark.parametrize("exit_code,method,expected", [
    (0, "claude.ai", "ready"), (1, "none", "signed_out"), (0, "api_key", "wrong_account"),
])
async def test_login_status(monkeypatch, exit_code, method, expected):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: "claude")

    class Process:
        returncode = exit_code

        async def communicate(self):
            return json.dumps({"authMethod": method}).encode(), b""

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(claude_code.asyncio, "create_subprocess_exec", spawn)
    assert (await claude_code.auth_status())["status"] == expected


async def test_missing_cli_is_reported_without_fallback(monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: None)
    assert (await claude_code.auth_status())["status"] == "unavailable"
    with pytest.raises(claude_code.BridgeUnavailable, match="non installato"):
        await claude_code.call("claude-sonnet-5-5", {"messages": []})


@pytest.mark.parametrize("error,expected", [
    ('{"error":"model not found"}', ProviderError),
    ("Login expired", claude_code.BridgeUnavailable),
])
async def test_cli_failure_distinguishes_model_from_login(monkeypatch, error, expected):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: "claude")

    async def ready():
        return {"status": "ready"}

    monkeypatch.setattr(claude_code, "auth_status", ready)

    class Process:
        returncode = 1

        async def communicate(self, prompt):
            return b"", error.encode()

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(claude_code.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(expected, match="model not found|Accesso Claude Code"):
        await claude_code.call("claude-sonnet-5-5", {"messages": []})


async def test_cli_stream_reports_agent_progress():
    async def runner(kwargs, on_event):
        await on_event("tool_use", "memory_search")
        return claude_code._response({"structured_output": {"text": "done", "tool_calls": []}})

    async with claude_code.ClaudeStream(runner, {}) as stream:
        events = [event async for event in stream]
        result = await stream.get_final_message()
    assert events[0].content_block.name == "memory_search"
    assert result.content[0].text == "done"


async def test_cli_stream_json_is_forwarded(monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: "claude")

    async def ready():
        return {"status": "ready"}

    monkeypatch.setattr(claude_code, "auth_status", ready)
    events = []

    class Input:
        def write(self, data):
            assert b"saluta" in data

        async def drain(self):
            pass

        def close(self):
            pass

    class Errors:
        async def read(self):
            return b""

    class Process:
        returncode = 0
        stdin = Input()
        stderr = Errors()

        def __init__(self):
            self.stdout = asyncio.StreamReader()
            for item in (
                {"type": "stream_event", "event": {"type": "content_block_start", "content_block": {"type": "text"}}},
                {"type": "result", "structured_output": {"text": "Ciao", "tool_calls": []}},
            ):
                self.stdout.feed_data((json.dumps(item) + "\n").encode())
            self.stdout.feed_eof()

        async def wait(self):
            return 0

    async def spawn(*args, **kwargs):
        assert "stream-json" in args and "--include-partial-messages" in args
        return Process()

    monkeypatch.setattr(claude_code.asyncio, "create_subprocess_exec", spawn)

    async def on_event(kind, name):
        events.append(kind)

    result = await claude_code.call("claude-sonnet-5-5", {"messages": [
        {"role": "user", "content": "saluta"}]}, on_event=on_event)
    assert events == ["text"] and result.content[0].text == "Ciao"


def test_auth_status_endpoint_reports_mode(make_hq, settings, monkeypatch):
    settings.claude_auth_mode = "subscription"
    settings.claude_subscription_enabled = True

    async def ready():
        return {"status": "ready", "detail": "ok"}

    monkeypatch.setattr(claude_code, "auth_status", ready)
    with TestClient(create_app(settings, hq=make_hq([]), start_workers=False)) as client:
        data = client.get("/api/claude/auth").json()
        assert data["mode"] == "subscription" and data["subscription"]["status"] == "ready"


async def test_subscription_agent_uses_hubnex_tool_without_api_credit(make_hq, settings, monkeypatch):
    settings.claude_auth_mode = "subscription"
    settings.claude_subscription_enabled = True
    hq = make_hq([])
    replies = iter([
        {"text": "", "tool_calls": [{"name": "memory_save", "input": {
            "topic": "Garage", "content": "Il garage si chiude alle 22"}}]},
        {"text": "Me lo ricordo.", "tool_calls": []},
    ])

    async def fake_cli(*args, **kwargs):
        return claude_code._response({"structured_output": next(replies), "usage": {
            "input_tokens": 20, "output_tokens": 5}})

    monkeypatch.setattr(claude_code, "call", fake_cli)
    answer = await hq.chat("dashboard", "ricorda che il garage si chiude alle 22")
    assert answer == "Me lo ricordo."
    assert "Il garage si chiude alle 22" in str(await hq.store.memories())
    assert hq.client.requests == []
    assert sum(r["cost"] for r in await hq.store.usage_by("model", "2000-01-01", "2999-12-31")) == 0
