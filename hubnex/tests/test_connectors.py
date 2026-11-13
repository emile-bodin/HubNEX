"""Connectors (MCP): the agents read freely, changes wait for the owner's ✅."""

import json

import httpx
import pytest

from hubnex.actions import ActionClosed
from hubnex.config import ConnectorSpec, _connectors
from hubnex.connectors import Connectors, needs_confirmation, tool_name
from hubnex.context import CURRENT_CHAT
from tests.conftest import FakeTeam, response, text_block, tool_block

TOOLS = [
    {"name": "cerca_clienti", "description": "Cerca clienti per nome.", "annotations": {"readOnlyHint": True},
     "inputSchema": {"type": "object", "properties": {"nome": {"type": "string"}}}},
    {"name": "crea_memo", "title": "Crea un memo", "description": "Crea un memo.",
     "inputSchema": {"type": "object", "properties": {"titolo": {"type": "string"}}}},
    {"name": "get_ordini", "description": "Ordini aperti (nessuna annotazione).",
     "inputSchema": {"type": "object", "properties": {}}},
]


class FakeMCP:
    """An MCP server over Streamable HTTP; answers tools/call with SSE to cover both formats."""

    def __init__(self, token="segreto"):
        self.token = token
        self.calls = []
        self.sessions = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401)
        msg = json.loads(request.content)
        method = msg.get("method")
        if method == "initialize":
            self.sessions += 1
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}}},
                                  headers={"Mcp-Session-Id": f"s{self.sessions}"})
        assert request.headers.get("mcp-session-id") == f"s{self.sessions}"
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": TOOLS}})
        if method == "tools/call":
            self.calls.append((msg["params"]["name"], msg["params"]["arguments"]))
            result = {"content": [{"type": "text", "text": f"ok {msg['params']['name']}"}]}
            body = f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': result})}\n\n"
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
        return httpx.Response(400)


def setup(make_hq, agents=None, token="segreto"):
    fake = FakeMCP()
    team = FakeTeam()
    hq = make_hq([], team=team)
    spec = ConnectorSpec(name="Gestionale", url="https://gestionale.example/mcp", token=token, agents=agents)
    hq.connectors = Connectors(hq, [spec], transport=httpx.MockTransport(fake.handler))
    CURRENT_CHAT.set(-100)
    return hq, fake, team


def test_config_and_rules():
    specs = _connectors([{"name": "Gestionale", "url": "https://x/mcp", "token": "t", "agents": ["boss", "technical"], "free": ["crea_bozza"]}])
    s = specs[0]
    assert s.headers() == {"Authorization": "Bearer t"} and s.allows("jarvis") and s.allows("technical") and not s.allows("mail")
    assert _connectors([{"name": "X", "url": "https://x"}])[0].allows("mail")  # no list: everybody
    with pytest.raises(ValueError, match="confirm"):
        _connectors([{"name": "X", "url": "https://x", "confirm": "forse"}])
    assert not needs_confirmation(s, TOOLS[0]) and needs_confirmation(s, TOOLS[1]) and not needs_confirmation(s, TOOLS[2])
    assert not needs_confirmation(s, {"name": "crea_bozza"})  # listed as free
    assert tool_name("Gestionale Ufficio", "crea memo!") == "gestionale_ufficio__crea_memo_"


async def test_agents_read_freely_and_changes_wait_for_confirmation(make_hq):
    hq, fake, team = setup(make_hq)
    hq.client.responses = [
        response([tool_block("gestionale__cerca_clienti", {"nome": "Bianchi"}, "t1")], "tool_use"),
        response([tool_block("gestionale__crea_memo", {"titolo": "Richiamare Bianchi"}, "t2")], "tool_use"),
        response([text_block("Fatto, ho proposto il memo.")], "end_turn"),
    ]
    await hq.chat("dashboard", "cerca Bianchi e crea un memo")
    tools = {t["name"] for t in hq.client.requests[0]["tools"]}
    assert {"gestionale__cerca_clienti", "gestionale__crea_memo", "gestionale__get_ordini"} <= tools
    assert fake.calls == [("cerca_clienti", {"nome": "Bianchi"})]  # the write did not run
    second = hq.client.requests[2]["messages"][-1]["content"][0]["content"]
    assert "NON è ancora stata eseguita" in second
    post = team.posts[-1]
    assert "GESTIONALE #1" in post["text"] and "• titolo: Richiamare Bianchi" in post["text"]
    assert [b[1] for b in post["buttons"][0]] == ["a:1:ok", "a:1:no"]

    note = await hq.actions.decide(1, True)
    assert fake.calls[-1] == ("crea_memo", {"titolo": "Richiamare Bianchi"}) and note == "✅ fatto: ok crea_memo"
    with pytest.raises(ActionClosed):
        await hq.actions.decide(1, True)
    assert len(fake.calls) == 2


async def test_connectors_only_for_the_listed_agents_and_errors_are_shown(make_hq):
    hq, fake, _ = setup(make_hq, agents=["technical"])
    assert await hq.connectors.tools_for("jarvis") == {}
    assert "gestionale__crea_memo" in await hq.connectors.tools_for("technical")

    hq, fake, _ = setup(make_hq, token="sbagliato")
    assert await hq.connectors.tools_for("jarvis") == {}
    assert "access denied" in (await hq.connectors.status())[0]
