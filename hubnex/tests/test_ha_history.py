"""The read-only history tools: mocked Home Assistant HTTP, a fake WebSocket watcher."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import httpx
import pytest

from hubnex.integrations.homeassistant import HomeAssistant
from hubnex.tools import REGISTRY, ToolContext
from hubnex.tools import ha_history as H
from tests.conftest import response, text_block

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def ago(**kw) -> str:
    return (NOW - timedelta(**kw)).isoformat()


class Watcher:
    enabled = True

    def __init__(self, states=(), ready=True, stats=None):
        self.states = {e: {"entity_id": e, "state": "on", "attributes": {}} for e in states}
        self.time_zone = "Europe/Rome"
        self.ready = asyncio.Event()
        if ready:
            self.ready.set()
        self.stats = stats or {}
        self.asked = []

    async def statistics(self, ids, start, end, period):
        self.asked.append((ids, start, end, period))
        if isinstance(self.stats, Exception):
            raise self.stats
        return self.stats


def make_ctx(handler, states=("binary_sensor.door", "light.kitchen"), **wkw):
    """A ToolContext on a real HomeAssistant client whose HTTP is `handler`."""
    seen = []

    def record(req: httpx.Request):
        seen.append(req)
        return handler(req)

    ha = HomeAssistant("http://ha:8123", "secret-token")
    ha._client = httpx.AsyncClient(base_url="http://ha:8123/api", transport=httpx.MockTransport(record))
    hq = NS(ha=ha, watcher=Watcher(states, **wkw))
    return ToolContext(hq, "jarvis", None), seen


async def run(name, ctx, **inp):
    return await REGISTRY[name].handler(ctx, inp)


def door_series():
    return [[
        {"entity_id": "binary_sensor.door", "state": "off", "last_changed": ago(hours=5)},
        {"state": "on", "last_changed": ago(hours=4)},
        {"state": "on", "last_changed": ago(hours=3, minutes=59)},
        {"state": "unavailable", "last_changed": ago(hours=3)},
        {"state": "on", "last_changed": ago(hours=2)},
        {"state": "off", "last_changed": ago(hours=1)},
    ]]


# ---------------------------------------------------------------------- ha_get_history
async def test_history_query_and_compact_local_output():
    ctx, seen = make_ctx(lambda r: httpx.Response(200, json=door_series()))
    out = await run("ha_get_history", ctx, entity_id="binary_sensor.door")
    req = seen[0]
    assert req.method == "GET" and req.url.path.startswith("/api/history/period/")
    q = req.url.params
    assert q["filter_entity_id"] == "binary_sensor.door" and q["end_time"]
    assert "minimal_response" in q and "significant_changes_only" in q and "no_attributes" in q
    # default window: the last 24 hours
    start = datetime.fromisoformat(req.url.path.rsplit("/", 1)[1])
    assert timedelta(hours=23, minutes=59) < datetime.fromisoformat(q["end_time"]) - start <= timedelta(hours=24)
    pts = out["entities"]["binary_sensor.door"]
    assert [p[1] for p in pts] == ["off", "on", "off"]  # repeats and unavailable gone
    from zoneinfo import ZoneInfo
    assert pts[0][0] == (NOW - timedelta(hours=5)).astimezone(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d %H:%M")
    assert out["time_zone"] == "Europe/Rome"
    assert "secret-token" not in json.dumps(out)


async def test_history_with_attributes_asks_for_them():
    series = [[
        {"entity_id": "climate.living", "state": "heat", "last_changed": ago(hours=3), "attributes": {"temperature": 20, "x": 1}},
        {"entity_id": "climate.living", "state": "heat", "last_changed": ago(hours=2), "attributes": {"temperature": 21, "x": 2}},
    ]]
    ctx, seen = make_ctx(lambda r: httpx.Response(200, json=series), states=["climate.living"])
    out = await run("ha_get_history", ctx, entity_id="climate.living", include_attributes=["temperature"])
    assert "minimal_response" not in seen[0].url.params and "no_attributes" not in seen[0].url.params
    assert [p[1:] for p in out["entities"]["climate.living"]] == [["heat", {"temperature": 20}], ["heat", {"temperature": 21}]]


async def test_history_range_is_limited_to_14_days():
    ctx, seen = make_ctx(lambda r: httpx.Response(200, json=door_series()))
    out = await run("ha_get_history", ctx, entity_id="binary_sensor.door", start="20d")
    start = datetime.fromisoformat(seen[0].url.path.rsplit("/", 1)[1])
    end = datetime.fromisoformat(seen[0].url.params["end_time"])
    assert end - start == timedelta(days=14)
    assert any("14 days" in n for n in out["notes"])


async def test_wildcards_unknown_ids_and_the_entity_cap():
    sensors = [f"binary_sensor.s{i:02d}" for i in range(30)]
    ctx, seen = make_ctx(lambda r: httpx.Response(200, json=[]), states=[*sensors, "light.kitchen"])
    out = await run("ha_get_history", ctx, entity_id="binary_sensor.*, sensor.nope")
    asked = seen[0].url.params["filter_entity_id"].split(",")
    assert len(asked) == 25 and all(a.startswith("binary_sensor.") for a in asked)
    assert "No state changes" in out and "Unknown: sensor.nope" in out and "first 25" in out

    with pytest.raises(LookupError, match="unknown entity: sensor.nope"):
        await run("ha_get_history", ctx, entity_id="sensor.nope")


async def test_wildcard_resolved_over_rest_when_the_websocket_is_down():
    def handler(r):
        if r.url.path == "/api/states":
            return httpx.Response(200, json=[{"entity_id": "person.anna", "state": "home", "attributes": {}},
                                             {"entity_id": "light.x", "state": "on", "attributes": {}}])
        return httpx.Response(200, json=[[{"entity_id": "person.anna", "state": "home", "last_changed": ago(hours=2)}]])

    ctx, seen = make_ctx(handler, states=(), ready=False)
    out = await run("ha_get_history", ctx, entity_id="person.*")
    assert seen[-1].url.params["filter_entity_id"] == "person.anna"
    assert out["entities"]["person.anna"][0][1] == "home"


async def test_http_errors_and_timeouts_are_short_messages():
    ctx, _ = make_ctx(lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(Exception, match="HA 500"):
        await run("ha_get_history", ctx, entity_id="binary_sensor.door")

    def slow(r):
        raise httpx.ReadTimeout("timed out", request=r)

    ctx, _ = make_ctx(slow)
    with pytest.raises(Exception, match="(?i)non raggiungibile|not reachable|unreachable"):
        await run("ha_get_history", ctx, entity_id="binary_sensor.door")


async def test_too_long_output_is_cut_with_a_note():
    pts = [{"entity_id": "sensor.power", "state": str(i), "last_changed": ago(minutes=2000 - i)} for i in range(2000)]
    ctx, _ = make_ctx(lambda r: httpx.Response(200, json=[pts]), states=["sensor.power"])
    out = await run("ha_get_history", ctx, entity_id="sensor.power")
    assert len(json.dumps(out)) <= H.MAX_CHARS
    assert out["entities"]["sensor.power"][-1][1] == "1999"  # the newest stay
    assert any("ha_summarize_history" in n for n in out["notes"])


async def test_bad_times_are_explained():
    ctx, _ = make_ctx(lambda r: httpx.Response(200, json=[]))
    with pytest.raises(ValueError, match="could not read the time"):
        await run("ha_get_history", ctx, entity_id="binary_sensor.door", start="yesterday-ish")
    with pytest.raises(ValueError, match="start must be before end"):
        await run("ha_get_history", ctx, entity_id="binary_sensor.door", start="1h", end="2h")


# ---------------------------------------------------------------------- ha_get_logbook
async def test_logbook_whole_house_and_one_entity():
    entries = [
        {"when": ago(hours=3), "name": "Front door", "message": "opened", "entity_id": "binary_sensor.door"},
        {"when": ago(hours=3), "name": "Front door", "message": "opened", "entity_id": "binary_sensor.door"},
        {"when": ago(hours=2), "name": "Front door", "message": "became unavailable", "entity_id": "binary_sensor.door"},
        {"when": ago(hours=1), "name": "Kitchen", "state": "on", "entity_id": "light.kitchen"},
    ]
    ctx, seen = make_ctx(lambda r: httpx.Response(200, json=entries))
    out = await run("ha_get_logbook", ctx)
    assert seen[0].url.path.startswith("/api/logbook/") and "entity" not in seen[0].url.params
    assert [e[1:3] for e in out["entries"]] == [["Front door", "opened"], ["Kitchen", "changed to on"]]

    await run("ha_get_logbook", ctx, entity_id="light.kitchen", start="2d")
    assert seen[-1].url.params["entity"] == "light.kitchen"


async def test_empty_logbook():
    ctx, _ = make_ctx(lambda r: httpx.Response(200, json=[]))
    assert (await run("ha_get_logbook", ctx)).startswith("No logbook entries for the house")


# ---------------------------------------------------------------------- ha_get_statistics
async def test_statistics_over_the_websocket():
    ms = int((NOW - timedelta(days=2)).timestamp() * 1000)
    stats = {"sensor.energy": [{"start": ms, "end": ms + 86400000, "sum": 120.456, "change": 8.123, "mean": None}]}
    ctx, seen = make_ctx(lambda r: httpx.Response(200, json=[]), stats=stats)
    out = await run("ha_get_statistics", ctx, statistic_id="sensor.energy, sensor.none", period="day", start="60d")
    ids, start, end, period = ctx.hq.watcher.asked[0]
    assert ids == ["sensor.energy", "sensor.none"] and period == "day"
    assert out["statistics"]["sensor.energy"] == {"columns": ["time", "sum", "change"],
                                                  "rows": [[H._fmt(ms, H.ZoneInfo("Europe/Rome"), day=True), 120.46, 8.12]]}
    assert out["no_statistics"] == ["sensor.none"]
    assert seen == []  # nothing over REST


async def test_statistics_need_the_websocket():
    ctx, _ = make_ctx(lambda r: httpx.Response(200, json=[]), ready=False)
    with pytest.raises(RuntimeError, match="WebSocket not connected"):
        await run("ha_get_statistics", ctx, statistic_id="sensor.energy")
    ctx, _ = make_ctx(lambda r: httpx.Response(200, json=[]), stats={})
    assert "No statistics" in await run("ha_get_statistics", ctx, statistic_id="sensor.energy")


# ---------------------------------------------------------------------- ha_summarize_history
async def test_summary_counts_time_in_state_and_weekday_times():
    tz = H.ZoneInfo("Europe/Rome")
    monday = (datetime.now(tz) - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    monday -= timedelta(days=monday.weekday())
    series = [{"entity_id": "light.kitchen", "state": "off", "last_changed": monday.isoformat()}]
    for day in range(2):  # Monday and Tuesday: on at 07:00/07:10, off at 23:00
        d = monday + timedelta(days=day)
        series += [{"state": "on", "last_changed": (d + timedelta(hours=7, minutes=10 * day)).isoformat()},
                   {"state": "off", "last_changed": (d + timedelta(hours=8)).isoformat()},
                   {"state": "on", "last_changed": (d + timedelta(hours=19)).isoformat()},
                   {"state": "off", "last_changed": (d + timedelta(hours=23)).isoformat()}]
    power = [{"entity_id": "sensor.power", "state": "100", "last_changed": (monday + timedelta(hours=34)).isoformat()},
             {"state": "300", "last_changed": (monday + timedelta(hours=35)).isoformat()},
             {"state": "999", "last_changed": ago(minutes=1)}]  # after the window: ignored
    ctx, seen = make_ctx(lambda r: httpx.Response(200, json=[series, power]), states=["light.kitchen", "sensor.power"])
    out = await run("ha_summarize_history", ctx, entity_id="light.kitchen,sensor.power",
                    start=monday.isoformat(), end=(monday + timedelta(days=3)).isoformat())
    light = out["entities"]["light.kitchen"]
    assert light["changes"] == 8
    assert light["time_in_state"]["on"]["hours"] == 9.8  # 5h on Monday, 4h50 on Tuesday
    assert light["typical"]["mon"] == {"days": 1, "first_on": "07:00", "last_off": "23:00"}
    assert light["typical"]["tue"]["first_on"] == "07:10"
    p = out["entities"]["sensor.power"]
    assert p["min"] == 100 and p["max"] == 300


async def test_summary_accepts_a_domain():
    ctx, seen = make_ctx(lambda r: httpx.Response(200, json=[]), states=["light.a", "light.b", "switch.c"])
    out = await run("ha_summarize_history", ctx, entity_id="light")
    assert seen[0].url.params["filter_entity_id"] == "light.a,light.b"
    assert out.startswith("No history")


async def test_the_history_tools_only_read():
    ctx, seen = make_ctx(lambda r: httpx.Response(200, json=[]))
    for name in ("ha_get_history", "ha_summarize_history"):
        await run(name, ctx, entity_id="binary_sensor.door")
    await run("ha_get_logbook", ctx)
    assert seen and all(r.method == "GET" for r in seen)


async def test_not_configured():
    ctx = ToolContext(NS(ha=NS(enabled=False), watcher=Watcher()), "jarvis", None)
    with pytest.raises(RuntimeError, match="HA_URL"):
        await run("ha_get_history", ctx, entity_id="light.x")


# ---------------------------------------------------------------------- who gets them
def _tool_names(req):
    return {t.get("name") for t in req.get("tools", [])}


async def test_every_agent_and_jarvis_get_the_history_tools_with_home_assistant(make_hq):
    hq = make_hq([response([text_block("ok")], "end_turn"), response([text_block("ok")], "end_turn")])
    hq.ha = NS(enabled=True)
    await hq.run_agent("accountant", "check the deadlines")
    req = hq.client.requests[-1]
    assert set(H_TOOLS) <= _tool_names(req) and "ha_get_history" in req["system"]
    await hq.converse("t", "when did the door open?")
    assert set(H_TOOLS) <= _tool_names(hq.client.requests[-1])


async def test_without_home_assistant_nobody_gets_them(make_hq):
    hq = make_hq([response([text_block("ok")], "end_turn"), response([text_block("ok")], "end_turn")])
    await hq.run_agent("accountant", "check the deadlines")
    assert not set(H_TOOLS) & _tool_names(hq.client.requests[-1])
    assert "ha_get_history" not in hq.client.requests[-1]["system"]
    await hq.converse("t", "hello")
    assert not set(H_TOOLS) & _tool_names(hq.client.requests[-1])


H_TOOLS = ("ha_get_history", "ha_get_logbook", "ha_get_statistics", "ha_summarize_history")
