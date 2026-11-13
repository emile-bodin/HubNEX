"""brAIn's Home Assistant tools, ported and answered inside HubNEX (the built-in "casa" connector)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from hubnex.context import ORIGIN, VOICE
from hubnex.mcp_server import catalog
from tests import test_casa as T
from tests.conftest import response, text_block, tool_block


class FakeREST:
    """Home Assistant's REST API: records every request, answers the few the tests use."""

    def __init__(self):
        self.requests: list[tuple[str, str, object]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path.removeprefix("/api")
        self.requests.append((request.method, path, body))
        if path.startswith("/services/"):
            return httpx.Response(200, json=[])
        if path.startswith("/camera_proxy/"):
            return httpx.Response(200, content=b"\xff\xd8fake-jpeg\xff\xd9", headers={"content-type": "image/jpeg"})
        if path == "/config":
            return httpx.Response(200, json={"location_name": "Casa", "version": "2026.11.0", "components": []})
        if path.startswith("/states/"):
            return httpx.Response(404, text="not found")
        return httpx.Response(404, text="not found")

    def services(self) -> list[tuple[str, object]]:
        return [(p, b) for m, p, b in self.requests if p.startswith("/services/")]


@pytest.fixture
def casa(settings, make_hq):
    """An HQ with Home Assistant configured: the WebSocket and the REST API are fakes."""
    settings.ha_url, settings.ha_token = "http://ha:8123", "tok"
    holder = {}

    async def make(responses=()):
        hq = make_hq(list(responses))
        w, ws, task = await T.connected()
        hq.watcher = w
        rest = FakeREST()
        await hq.ha._client.aclose()
        hq.ha._client = httpx.AsyncClient(base_url="http://ha:8123/api", transport=httpx.MockTransport(rest.handler))
        holder["task"] = task
        return hq, rest

    yield make
    if "task" in holder:
        holder["task"].cancel()


def server(hq):
    return hq.connectors.items["casa"].client


async def test_only_the_ported_tools_of_the_groups_switched_on(casa):
    hq, _ = await casa()
    tools = {t["name"]: t for t in await server(hq).list_tools()}
    expected = set(catalog.tools_in(hq.settings.ha_mcp_groups))
    assert set(tools) == expected
    assert not {"list_dashboards", "minecraft_status", "recall", "get_findings"} & set(tools)
    assert tools["get_entity_state"]["annotations"]["readOnlyHint"] is True
    assert tools["control_light"]["annotations"]["readOnlyHint"] is False
    assert all("brain." not in t["description"] for t in tools.values())

    hq.settings.ha_mcp_groups = ("read", "dashboards")
    hq.settings.ha_mcp_exclude_tools = {"render_template"}
    names = {t["name"] for t in await server(hq).list_tools()}
    assert "list_dashboards" in names and "control_light" not in names and "render_template" not in names


async def test_jarvis_gets_the_casa_tools_instead_of_the_basic_ones(casa):
    hq, _ = await casa([response([text_block("Ecco.")], "end_turn")])
    await hq.converse("dashboard", "com'è la casa?")
    req = hq.client.requests[0]
    names = {t["name"] for t in req["tools"]}
    assert {"casa__control_light", "casa__get_entity_state", "casa__get_automation_trace"} <= names
    assert not {"ha_call_service", "ha_get_state", "ha_list_entities"} & names
    assert "ha_get_history" in names  # HubNEX's own history tools stay
    assert catalog.INSTRUCTIONS in req["system"]


async def test_a_light_is_switched_and_written_down(casa):
    hq, rest = await casa()
    events = hq.subscribe()
    out, failed = await server(hq).call_tool("control_light", {"entity_id": "light.lampada", "action": "turn_on",
                                                                "brightness_pct": 40}, agent_id="jarvis")
    assert not failed, out
    assert rest.services() == [("/services/light/turn_on", {"entity_id": "light.lampada", "brightness_pct": 40})]
    await asyncio.sleep(0.05)  # the ledger row is written on the event loop
    rows = await hq.store.ha_actions()
    assert rows[0]["service"] == "light.turn_on" and rows[0]["entities"] == ["light.lampada"]
    assert rows[0]["agent_id"] == "jarvis" and rows[0]["channel"] == "chat"
    seen = []
    while not events.empty():
        seen.append(events.get_nowait())
    assert any(e["type"] == "log" and "light.turn_on" in e["entry"]["text"] for e in seen)


async def test_states_come_from_memory(casa):
    hq, rest = await casa()
    out, failed = await server(hq).call_tool("get_entity_state", {"entity_id": "light.lampada"})
    assert not failed and json.loads(out)["entity_id"] == "light.lampada"
    assert not [r for r in rest.requests if r[1].startswith("/states")]


async def test_protected_entities_and_routines_cannot_act(casa):
    hq, rest = await casa()
    hq.settings.ha_protected_entities = ("light.lampada",)
    out, failed = await server(hq).call_tool("control_light", {"entity_id": "light.lampada", "action": "turn_on"})
    assert failed and not rest.services()

    hq.settings.ha_protected_entities = ()
    token = ORIGIN.set("routine")
    try:
        out, failed = await server(hq).call_tool("control_light", {"entity_id": "light.lampada", "action": "turn_on"})
    finally:
        ORIGIN.reset(token)
    assert failed and "owner" in out and not rest.services()


async def test_voice_has_its_own_deny_list(casa):
    hq, rest = await casa()
    hq.settings.ha_voice_exposed_only = False
    token = VOICE.set(True)
    try:
        out, failed = await server(hq).call_tool("call_service", {"domain": "lock", "service": "unlock",
                                                                  "data": {"entity_id": "lock.porta"}})
    finally:
        VOICE.reset(token)
    assert failed and not rest.services()
    # from the chat only ha_blocked_services counts (empty here): the owner may unlock
    out, failed = await server(hq).call_tool("call_service", {"domain": "lock", "service": "unlock",
                                                              "data": {"entity_id": "lock.porta"}})
    assert not failed and rest.services() == [("/services/lock/unlock", {"entity_id": "lock.porta"})]
    hq.settings.ha_blocked_services = {"lock.unlock"}
    out, failed = await server(hq).call_tool("call_service", {"domain": "lock", "service": "unlock",
                                                              "data": {"entity_id": "lock.porta"}})
    assert failed and len(rest.services()) == 1


async def test_camera_frames_come_back_as_images(casa):
    hq, rest = await casa()
    out, failed = await server(hq).call_tool("get_camera_snapshot", {"entity_id": "camera.ingresso"})
    assert not failed
    assert out[0]["type"] == "image" and out[0]["source"]["media_type"] == "image/jpeg"
    hq.settings.mcp_image_results = False
    out, failed = await hq.connectors.execute(
        (await hq.connectors.tools_for("jarvis"))["casa__get_camera_snapshot"], {"entity_id": "camera.ingresso"}, "jarvis")
    assert isinstance(out, str) and "[image]" in out


async def test_writes_not_marked_free_wait_for_the_owner(casa):
    hq, rest = await casa([
        response([tool_block("casa__control_lock", {"entity_id": "lock.porta", "action": "lock"})], "tool_use"),
        response([text_block("Ho chiesto conferma.")], "end_turn"),
    ])
    await hq.converse("dashboard", "chiudi la porta")
    assert not rest.services()  # proposed, not done
    actions = await hq.store.actions_open()
    assert actions and actions[0]["kind"] == "mcp" and "lock.porta" in actions[0]["summary"]
    await hq.actions.decide(actions[0]["id"], True)
    assert rest.services() == [("/services/lock/lock", {"entity_id": "lock.porta"})]


async def test_switched_off_on_the_addon_page(settings, make_hq):
    settings.ha_url, settings.ha_token = "http://ha:8123", "tok"
    settings.ha_mcp_enabled = False
    hq = make_hq([])
    assert "casa" not in hq.connectors.items


async def test_tool_search_offers_the_rest_on_request(casa):
    hq, _ = await casa([
        response([tool_block("mcp_search_tools", {"query": "automation trace"})], "tool_use"),
        response([tool_block("casa__get_automation_trace", {"automation_id": "x"}, "t2")], "tool_use"),
        response([text_block("Fatto.")], "end_turn"),
    ])
    hq.settings.mcp_tool_search = True
    await hq.converse("dashboard", "perché non è partita l'automazione?")
    first = {t["name"] for t in hq.client.requests[0]["tools"]}
    assert "mcp_search_tools" in first and "casa__get_automation_trace" not in first
    assert "casa__get_entity_state" in first  # always loaded
    second = {t["name"] for t in hq.client.requests[1]["tools"]}
    assert "casa__get_automation_trace" in second
    last = hq.client.requests[2]["messages"][-1]["content"][0]
    assert "non disponibile" not in str(last["content"])


def rpc(client, method, params=None, token="ext", mid=1):
    return client.post("/mcp", headers={"Authorization": f"Bearer {token}"},
                       json={"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


def test_mcp_endpoint_is_off_unless_switched_on(settings, make_hq):
    from fastapi.testclient import TestClient
    from hubnex.main import create_app

    settings.hq_token = "t"
    with TestClient(create_app(settings, hq=make_hq([]), start_workers=False)) as client:
        assert rpc(client, "initialize", token="t").status_code == 404


def test_mcp_endpoint_offers_sessions_and_team(settings, make_hq):
    from fastapi.testclient import TestClient
    from hubnex.main import create_app

    settings.hq_token, settings.mcp_token = "t", "ext"
    settings.mcp_expose, settings.mcp_expose_tools = True, ("sessions", "team")
    hq = make_hq([response([text_block("Ciao dal server.")], "end_turn")])
    hq.settings.model_voice = ""
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        assert rpc(client, "initialize", token="wrong").status_code == 401
        init = rpc(client, "initialize", {"protocolVersion": "2025-06-18"}).json()["result"]
        assert init["serverInfo"]["name"] == "hubnex" and "read-only" in init["instructions"]
        assert client.post("/mcp", headers={"Authorization": "Bearer ext"},
                           json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
        names = {t["name"] for t in rpc(client, "tools/list").json()["result"]["tools"]}
        assert names == {"list_sessions", "get_session", "team_status"}  # read-only: no ask/give
        status = rpc(client, "tools/call", {"name": "team_status", "arguments": {}}).json()["result"]
        assert "jarvis" in status["content"][0]["text"]
        refused = rpc(client, "tools/call", {"name": "ask_jarvis", "arguments": {"text": "x"}}).json()["result"]
        assert refused["isError"]

        hq.settings.mcp_expose_read_only = False
        out = rpc(client, "tools/call", {"name": "ask_jarvis", "arguments": {"text": "ciao"}}).json()["result"]
        answer = json.loads(out["content"][0]["text"])
        assert answer["reply"] == "Ciao dal server."
        listing = json.loads(rpc(client, "tools/call", {"name": "list_sessions", "arguments": {"channel": "mcp"}})
                             .json()["result"]["content"][0]["text"])
        assert [s["id"] for s in listing] == [answer["session_id"]]
        assert rpc(client, "nope").json()["error"]["code"] == -32601


async def test_mcp_endpoint_offers_the_house_tools(casa):
    from hubnex.mcp_server.expose import Exposed

    hq, rest = await casa()
    hq.settings.mcp_expose_tools = ("ha",)
    ex = Exposed(hq)
    names = {t["name"] for t in await ex.tools()}
    assert "get_entity_state" in names and "control_light" not in names  # read-only by default
    out = await ex.call("get_camera_snapshot", {"entity_id": "camera.ingresso"})
    assert out["content"][0]["type"] == "image" and out["content"][0]["mimeType"] == "image/jpeg"
    hq.settings.mcp_expose_read_only = False
    out = await ex.call("control_light", {"entity_id": "light.lampada", "action": "turn_off"})
    assert not out.get("isError") and rest.services() == [("/services/light/turn_off", {"entity_id": "light.lampada"})]
