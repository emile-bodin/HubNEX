"""House view: Home Assistant areas and entities on the floor plan, live, editable from the dashboard."""

import asyncio
import json

import pytest
import yaml
from fastapi.testclient import TestClient

from hubnex.casa import LayoutError, parse_layout
from hubnex.integrations.ha_ws import HAWatcher, websocket_url
from hubnex.main import create_app
from tests.conftest import response, text_block

AREAS = [{"area_id": "sala", "name": "Sala da Pranzo"}, {"area_id": "soggiorno", "name": "Soggiorno"},
         {"area_id": "giardino", "name": "Giardino"}, {"area_id": "garage", "name": "Parcheggio"}]
DEVICES = [{"id": "dev-lampadario", "area_id": "sala"}]
ENTITIES = [
    {"entity_id": "light.lampadario", "device_id": "dev-lampadario", "area_id": None},  # area from its device
    {"entity_id": "light.lampada", "device_id": None, "area_id": "soggiorno"},
    {"entity_id": "sensor.lampada_rssi", "device_id": None, "area_id": "soggiorno", "entity_category": "diagnostic"},
    {"entity_id": "switch.vecchia", "device_id": None, "area_id": "soggiorno", "disabled_by": "user"},
    {"entity_id": "switch.irrigazione", "device_id": None, "area_id": "giardino"},
    {"entity_id": "light.angolo", "device_id": None, "area_id": None},
]


def st(eid, state, **attrs):
    return {"entity_id": eid, "state": state, "attributes": attrs}


STATES = [
    st("light.lampadario", "on", friendly_name="Lampadario", brightness=153),
    st("light.lampada", "off", friendly_name="Lampada da terra"),
    st("sensor.lampada_rssi", "-60"),
    st("switch.irrigazione", "off", friendly_name="Irrigazione"),
    st("light.angolo", "off", friendly_name="Lampada angolo"),
    st("scene.cinema", "unknown", friendly_name="Cinema"),
    st("alarm_control_panel.casa", "armed_away", friendly_name="Allarme"),  # no area
    st("binary_sensor.no_unique_id", "off", friendly_name="Vecchio sensore"),
]

LAYOUT = """
floors:
  - name: Piano terra
    aspect: 1.06
    rooms:
      - { area: Balcone, x: 0, y: 0, w: 97.8, h: 85.8, outline: true }
      - { area: sala da pranzo, x: 48.6, y: 41.1, w: 38.2, h: 23 }
      - { area: Soggiorno, x: 44.1, y: 66.6, w: 31.2, h: 31.4 }
outside: [Giardino]
"""


class FakeWS:
    """A Home Assistant WebSocket: answers commands, can push events."""

    def __init__(self):
        self.sent = []
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.inbox.put_nowait({"type": "auth_required"})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def recv(self):
        return json.dumps(await self.inbox.get())

    def __aiter__(self):
        return self

    async def __anext__(self):
        msg = await self.inbox.get()
        if msg is None:
            raise StopAsyncIteration
        return json.dumps(msg)

    async def send(self, raw):
        msg = json.loads(raw)
        self.sent.append(msg)
        t = msg["type"]
        if t == "auth":
            self.inbox.put_nowait({"type": "auth_ok"} if msg["access_token"] == "tok" else {"type": "auth_invalid"})
            return
        result = {
            "config/area_registry/list": AREAS,
            "config/floor_registry/list": [],
            "config/device_registry/list": DEVICES,
            "config/entity_registry/list": ENTITIES,
            "get_states": STATES,
            "config/auth/list": USERS,
        }.get(t)
        if t == "config/entity_registry/get_entries":
            result = {eid: {"entity_id": eid, "aliases": ALIASES.get(eid, [])} for eid in msg["entity_ids"]}
        if t == "config/entity_registry/update":
            result = {"entity_entry": {"entity_id": msg["entity_id"], "area_id": msg["area_id"], "device_id": None}}
        self.inbox.put_nowait({"id": msg["id"], "type": "result", "success": True, "result": result})

    def push(self, event_type, data):
        self.inbox.put_nowait({"type": "event", "event": {"event_type": event_type, "data": data}})


# Aliases set in Home Assistant (entity settings → Aliases).
ALIASES = {"light.angolo": ["Luce dell'angolo", "abat-jour"]}

USERS = [
    {"id": "owner", "name": "Io", "is_owner": True, "group_ids": ["system-admin"]},
    {"id": "wife", "name": "Moglie", "is_owner": False, "group_ids": ["system-users"]},
]


async def connected(events=None):
    ws = FakeWS()

    async def on_event(kind, eid, state):
        if events is not None:
            events.append((kind, eid, state and state["state"]))

    w = HAWatcher("http://supervisor/core", "tok", on_event, connect=lambda url: ws)
    task = asyncio.create_task(w.run())
    await asyncio.wait_for(w.ready.wait(), 2)
    return w, ws, task


def test_websocket_url():
    assert websocket_url("http://supervisor/core") == "ws://supervisor/core/websocket"
    assert websocket_url("https://casa.example:8123/") == "wss://casa.example:8123/api/websocket"


async def test_watcher_loads_registries_and_follows_changes():
    events = []
    w, ws, task = await connected(events)
    assert ws.sent[0] == {"type": "auth", "access_token": "tok"}
    assert {"type": "subscribe_events", "event_type": "state_changed"} == {k: v for k, v in ws.sent[1].items() if k != "id"}
    assert w.area_of("light.lampadario") == "sala"  # inherited from the device
    assert w.area_of("light.lampada") == "soggiorno"
    ws.push("state_changed", {"entity_id": "light.lampada", "new_state": st("light.lampada", "on")})
    await asyncio.sleep(0.05)
    assert w.states["light.lampada"]["state"] == "on"
    assert ("state", "light.lampada", "on") in events
    await w.set_area("light.angolo", "soggiorno")
    assert ws.sent[-1]["type"] == "config/entity_registry/update" and ws.sent[-1]["area_id"] == "soggiorno"
    assert w.area_of("light.angolo") == "soggiorno"
    task.cancel()


async def test_rooms_follow_areas_with_the_owners_adjustments(make_hq):
    hq = make_hq([])
    w, ws, task = await connected()
    hq.casa.ha = hq.watcher = w
    hq.casa.save_layout(LAYOUT)
    view = hq.casa.build()
    areas = {a["id"]: a for a in view["areas"]}
    assert areas["sala"]["entities"] == ["light.lampadario"]
    assert areas["soggiorno"]["entities"] == ["light.lampada"]  # no diagnostic, no disabled
    assert areas["giardino"]["outside"] and areas["garage"]["placed"] is False  # not drawn: shown below the plan
    rooms = view["floors"][0]["rooms"]
    assert [r["area_id"] for r in rooms] == [None, "sala", "soggiorno"]  # Balcone is not an HA area: drawn only
    assert view["scenes"] == ["scene.cinema"]
    assert view["alarms"] == ["alarm_control_panel.casa"] and view["states"]["alarm_control_panel.casa"]["s"] == "armed_away"
    assert view["states"]["light.lampadario"] == {"s": "on", "n": "Lampadario", "k": "light", "a": {"brightness": 153}}

    await hq.casa.show_here("soggiorno", "binary_sensor.no_unique_id")  # dashboard only
    await hq.casa.hide("sala", "light.lampadario")
    areas = {a["id"]: a for a in hq.casa.build()["areas"]}
    assert areas["soggiorno"]["entities"] == ["binary_sensor.no_unique_id", "light.lampada"]
    assert areas["sala"]["entities"] == []
    assert [c["entity_id"] for c in hq.casa.candidates("angolo", "soggiorno")] == ["light.angolo"]
    task.cancel()


def test_layout_is_checked_before_saving(tmp_path):
    assert parse_layout(LAYOUT)["floors"][0]["rooms"][0]["outline"] is True
    with pytest.raises(LayoutError, match="outside the drawing"):
        parse_layout("floors: [{rooms: [{area: X, x: 90, y: 0, w: 20, h: 10}]}]")
    with pytest.raises(LayoutError, match="serve 'area'"):
        parse_layout("floors: [{rooms: [{x: 0, y: 0, w: 20, h: 10}]}]")
    with pytest.raises(LayoutError, match="YAML"):
        parse_layout("floors: [")


def test_polygon_rooms_validate_and_keep_their_bounds():
    points = [{"x": 10, "y": 10}, {"x": 70, "y": 10}, {"x": 70, "y": 30},
              {"x": 40, "y": 30}, {"x": 40, "y": 70}, {"x": 10, "y": 70}]
    layout = lambda p: yaml.safe_dump({"floors": [{"rooms": [{"area": "Hal", "points": p}]}]})
    room = parse_layout(layout(points))["floors"][0]["rooms"][0]
    assert (room["x"], room["y"], room["w"], room["h"]) == (10, 10, 60, 60)
    assert room["points"] == points
    with pytest.raises(LayoutError, match="Angoli fuori dal disegno"):
        parse_layout(layout([{**points[0], "x": 100.04}, *points[1:]]))
    with pytest.raises(LayoutError, match="incrocia"):
        parse_layout(layout([{"x": 10, "y": 10}, {"x": 70, "y": 70}, {"x": 70, "y": 10}, {"x": 10, "y": 70}]))


def test_dashboard_api(settings, make_hq):
    hq = make_hq([])
    calls = []

    class FakeREST:
        enabled = True

        async def call_service(self, domain, service, data, by_owner=False):
            calls.append((domain, service, data, by_owner))
            return []

        async def close(self):
            pass

    hq.ha = FakeREST()
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w

        r = client.put("/api/casa/layout", json={"text": "floors: ["})
        assert r.status_code == 422
        assert client.post("/api/casa/layout", json={"text": LAYOUT}).json() == {"ok": True}
        assert "Soggiorno" in client.get("/api/casa/layout").json()["text"]

        view = client.get("/api/casa").json()
        assert view["floors"][0]["rooms"][1]["name"] == "Sala da Pranzo"

        # Unlocking is blocked for Jarvis, not for the owner pressing the button.
        client.post("/api/casa/call", json={"domain": "lock", "service": "unlock", "data": {"entity_id": "lock.porta"}})
        assert calls == [("lock", "unlock", {"entity_id": "lock.porta"}, True)]

        assert client.post("/api/casa/rooms/soggiorno/entities", json={"entity_id": "light.angolo", "mode": "ha"}).json()["ok"]
        assert ws.sent[-1]["type"] == "config/entity_registry/update"
        r = client.post("/api/casa/rooms/soggiorno/entities", json={"entity_id": "binary_sensor.no_unique_id", "mode": "ha"})
        assert r.status_code == 409 and "solo alla plancia" in r.json()["detail"]
        client.post("/api/casa/rooms/soggiorno/entities", json={"entity_id": "binary_sensor.no_unique_id", "mode": "local"})
        client.post("/api/casa/rooms/soggiorno/entities/light.lampada/remove")
        soggiorno = next(a for a in client.get("/api/casa").json()["areas"] if a["id"] == "soggiorno")
        assert soggiorno["entities"] == ["binary_sensor.no_unique_id", "light.angolo"]
        client.portal.call(lambda: task.cancel())


async def test_live_changes_reach_the_dashboard(make_hq):
    hq = make_hq([])
    events = hq.subscribe()
    w, ws, task = await connected()
    hq.watcher = hq.casa.ha = w
    w.on_event = hq._ha_event
    hq.casa.build()
    ws.push("state_changed", {"entity_id": "light.lampada", "new_state": st("light.lampada", "on", friendly_name="Lampada da terra")})
    ws.push("state_changed", {"entity_id": "sensor.lampada_rssi", "new_state": st("sensor.lampada_rssi", "-61")})  # not shown
    ws.push("area_registry_updated", {})
    await asyncio.sleep(1.3)
    got = []
    while not events.empty():
        got.append(events.get_nowait())
    assert {"type": "ha", "e": "light.lampada", "v": {"s": "on", "n": "Lampada da terra", "k": "light", "a": {}}} in got
    assert not any(e.get("e") == "sensor.lampada_rssi" for e in got)
    assert {"type": "casa_changed"} in got
    task.cancel()


def test_layout_mistakes_are_explained_and_hand_edits_picked_up(make_hq, tmp_path):
    with pytest.raises(LayoutError, match="unknown key: plan"):
        parse_layout("plan:\n  - {area: X, x: 0, y: 0, w: 10, h: 10}")
    with pytest.raises(LayoutError, match="no floor"):
        parse_layout("outside: [Giardino]")
    # Italian keys and a single floor without "floors:" are fine.
    assert parse_layout("piani:\n  - nome: Terra\n    stanze:\n      - {area: X, x: 0, y: 0, w: 10, h: 10}")["floors"][0]["name"] == "Terra"
    assert parse_layout("rooms:\n  - {area: X, x: 0, y: 0, w: 10, h: 10}")["floors"][0]["rooms"][0]["area"] == "X"

    hq = make_hq([])
    assert hq.casa.build()["floors"] == []
    hq.casa.path.write_text(LAYOUT)  # written with File editor, no restart
    assert len(hq.casa.build()["floors"]) == 1
    hq.casa.path.write_text("floors: [")
    import os
    os.utime(hq.casa.path, (1, 1))
    view = hq.casa.build()
    assert "YAML" in view["layout_error"]


def test_owner_picks_the_rooms_temperature_sensor(settings, make_hq):
    hq = make_hq([])
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w
        assert client.post("/api/casa/rooms/sala/temperature", json={"entity_id": "sensor.temp_sala"}).json()["ok"]
        sala = next(a for a in client.get("/api/casa").json()["areas"] if a["id"] == "sala")
        assert sala["temp"] == "sensor.temp_sala"
        client.post("/api/casa/rooms/sala/temperature", json={"entity_id": None})
        assert next(a for a in client.get("/api/casa").json()["areas"] if a["id"] == "sala")["temp"] is None
        assert client.post("/api/casa/rooms/nessuna/temperature", json={}).status_code == 404
        client.portal.call(lambda: task.cancel())


def test_entities_can_be_shown_as_another_kind(settings, make_hq):
    hq = make_hq([])
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w
        assert client.post("/api/casa/entities/switch.irrigazione/kind", json={"kind": "light"}).json()["ok"]
        view = client.get("/api/casa").json()
        assert view["states"]["switch.irrigazione"]["k"] == "light" and view["states"]["switch.irrigazione"]["nk"] == "switch"
        assert client.post("/api/casa/entities/switch.irrigazione/kind", json={"kind": "razzo"}).status_code == 422
        client.post("/api/casa/entities/light.lampadario/kind", json={"kind": "siren"})
        assert client.get("/api/casa").json()["states"]["light.lampadario"]["k"] == "siren"
        client.post("/api/casa/entities/switch.irrigazione/kind", json={"kind": None})
        assert "nk" not in client.get("/api/casa").json()["states"]["switch.irrigazione"]
        client.portal.call(lambda: task.cancel())


def test_camera_frames_come_through_the_addon(settings, make_hq):
    hq = make_hq([])

    class FakeREST:
        enabled = True

        async def camera_image(self, eid):
            return b"\xff\xd8jpeg", "image/jpeg"

        async def camera_stream(self, eid):
            async def chunks():
                yield b"--f\r\n"
                yield b"frame"
            return "multipart/x-mixed-replace; boundary=f", chunks()

        async def close(self):
            pass

    hq.ha = FakeREST()
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w
        r = client.get("/api/casa/camera/camera.ingresso?t=1")
        assert r.content == b"\xff\xd8jpeg" and r.headers["content-type"] == "image/jpeg"
        assert client.get("/api/casa/camera/light.lampadario").status_code == 404
        r = client.get("/api/casa/camera/camera.ingresso/stream")
        assert r.headers["content-type"].startswith("multipart/x-mixed-replace") and r.content == b"--f\r\nframe"
        client.portal.call(lambda: task.cancel())


def _plan_png(fmt="PNG"):
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1000, 800), "white")  # a drawing in the middle of a white sheet
    ImageDraw.Draw(img).rectangle((300, 200, 700, 600), outline="black", width=6)
    out = io.BytesIO()
    img.save(out, fmt)
    return out.getvalue()


def test_plan_images_are_trimmed_and_pdfs_rendered():
    from hubnex.casa import plan_image

    jpg, aspect = plan_image(_plan_png())
    assert jpg[:2] == b"\xff\xd8" and 0.9 < aspect < 1.1  # only the square drawing is left
    jpg, aspect = plan_image(_plan_png("PDF"))
    assert jpg[:2] == b"\xff\xd8" and 0.9 < aspect < 1.1
    with pytest.raises(LayoutError, match="format not recognised"):
        plan_image(b"not an image")


def test_editor_saves_the_plan_and_ai_proposes_rooms(settings, make_hq):
    import json as _json

    hq = make_hq([response([text_block(_json.dumps({"rooms": [
        {"label": "Sala", "area": "sala da pranzo", "x": 10, "y": 10, "w": 40, "h": 30, "outline": False},
        {"label": "Ripostiglio", "area": "", "x": 95, "y": 90, "w": 20, "h": 30, "outline": False},
        {"label": "Hal", "area": "", "x": 10, "y": 10, "w": 60, "h": 60, "outline": False,
         "points": [{"x": 10, "y": 10}, {"x": 70, "y": 10}, {"x": 70, "y": 30},
                    {"x": 40, "y": 30}, {"x": 40, "y": 70}, {"x": 10, "y": 70}]},
        {"label": "Fout", "area": "", "x": 0, "y": 0, "w": 50, "h": 50, "outline": False,
         "points": [{"x": 10, "y": 10}, {"x": 70, "y": 70}, {"x": 70, "y": 10}, {"x": 10, "y": 70}]},
    ]}))], "end_turn")])
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w
        up = client.post("/api/casa/plan-image?floor=1", content=_plan_png()).json()
        assert up["image"] == "pianta-1.jpg" and client.get("/api/casa/plan-image/pianta-1.jpg").content[:2] == b"\xff\xd8"
        assert client.get("/api/casa/plan-image/..%2Fcasa.yaml").status_code == 404

        suggestion = client.post("/api/casa/plan-suggest", json={"image": "pianta-1.jpg"}).json()
        rooms = suggestion["rooms"]
        assert rooms[0] == {"area": "Sala da Pranzo", "linked": True, "x": 10.0, "y": 10.0, "w": 40.0, "h": 30.0, "outline": False}
        assert rooms[1]["area"] == "Ripostiglio" and not rooms[1]["linked"] and rooms[1]["w"] == 5.0  # kept inside
        assert suggestion["skipped"] == 1 and rooms[2]["points"][3] == {"x": 40.0, "y": 30.0}
        req = hq.client.requests[0]
        assert req["messages"][0]["content"][0]["type"] == "image" and "Sala da Pranzo" in req["messages"][0]["content"][1]["text"]

        plan = {"floors": [{"name": "Terra", "aspect": up["aspect"], "image": up["image"],
                            "rooms": [{"area": r["area"], **({"points": r["points"]} if r.get("points") else
                                      {k: r[k] for k in ("x", "y", "w", "h")})} for r in rooms]}],
                "outside": ["Giardino"]}
        assert client.post("/api/casa/plan", json=plan).json() == {"ok": True}
        view = client.get("/api/casa").json()
        assert view["floors"][0]["image"] == "pianta-1.jpg" and view["floors"][0]["rooms"][0]["area_id"] == "sala"
        assert view["floors"][0]["rooms"][2]["w"] == 60 and view["floors"][0]["rooms"][2]["points"] == rooms[2]["points"]
        assert "Sala da Pranzo" in client.get("/api/casa/layout").json()["text"]  # still a readable YAML
        client.portal.call(lambda: task.cancel())


def test_users_who_are_not_admins_only_get_the_house(settings, make_hq):
    settings.trusted_proxy = "testclient"  # TestClient plays the Supervisor's ingress proxy
    hq = make_hq([])
    calls = []

    class FakeREST:
        enabled = True

        async def call_service(self, domain, service, data, by_owner=False):
            calls.append((domain, service))
            return []

        async def close(self):
            pass

    hq.ha = FakeREST()
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w
        wife, owner = {"X-Remote-User-Id": "wife"}, {"X-Remote-User-Id": "owner"}

        assert client.get("/api/casa", headers=wife).status_code == 200
        assert client.post("/api/casa/call", headers=wife, json={"domain": "light", "service": "turn_off", "data": {"entity_id": "light.lampada"}}).status_code == 200
        assert client.post("/api/casa/call", headers=wife, json={"domain": "hassio", "service": "addon_stop", "data": {}}).status_code == 403
        assert calls == [("light", "turn_off")]
        for method, path, body in [("get", "/api/state", None), ("post", "/api/chat", {"text": "ciao"}),
                                   ("get", "/api/logs", None), ("post", "/api/casa/plan", {"floors": []}),
                                   ("post", "/api/casa/rooms/soggiorno/entities", {"entity_id": "light.angolo", "mode": "ha"})]:
            r = getattr(client, method)(path, headers=wife, **({"json": body} if body else {}))
            assert r.status_code == 403, path
        assert client.get("/api/state", headers=owner).status_code == 200
        assert client.get("/api/state").status_code == 403  # nobody named: house only

        with client.websocket_connect("/ws", headers=wife) as sock:
            state = sock.receive_json()["state"]
            assert state["role"] == "casa" and state["logs"] == [] and state["integrations"]["home_assistant"]
        with client.websocket_connect("/ws", headers=owner) as sock:
            assert sock.receive_json()["state"]["agents"]

        settings.non_admin_access = "completo"
        assert client.get("/api/state", headers=wife).status_code == 200
        client.portal.call(lambda: task.cancel())


async def test_aliases_set_in_home_assistant_name_the_entities(make_hq):
    hq = make_hq([])
    w, ws, task = await connected()
    hq.casa.ha = hq.watcher = w
    assert w.entities["light.angolo"]["aliases"] == ["Luce dell'angolo", "abat-jour"]
    assert hq.casa.compact("light.angolo")["n"] == "Luce dell'angolo"
    assert "aliases" not in w.entities["light.lampada"]
    found = [c["entity_id"] for c in hq.casa.candidates("abat-jour", "soggiorno")]
    assert found == ["light.angolo"]
    task.cancel()


async def test_anything_in_home_assistant_can_be_added_and_people_are_shown(make_hq):
    hq = make_hq([])
    w, ws, task = await connected()
    hq.casa.ha = hq.watcher = w
    w.states["media_player.salotto"] = st("media_player.salotto", "playing", friendly_name="Salotto", media_title="Radio", volume_level=0.3)
    w.entities["media_player.salotto"] = {"entity_id": "media_player.salotto", "area_id": None, "hidden_by": "integration"}
    w.states["person.anna"] = st("person.anna", "home", friendly_name="Anna")
    w.states["number.timer_irrigazione"] = st("number.timer_irrigazione", "10", friendly_name="Timer irrigazione")
    w.states["switch.vecchia"] = st("switch.vecchia", "off")  # disabled in Home Assistant: never offered
    found = [c["entity_id"] for c in hq.casa.candidates("", "soggiorno", limit=100)]
    assert {"media_player.salotto", "person.anna", "number.timer_irrigazione"} <= set(found)
    assert "switch.vecchia" not in found
    assert found.index("light.angolo") < found.index("media_player.salotto")  # the usual devices first
    salotto = next(c for c in hq.casa.candidates("salotto", "soggiorno"))
    assert salotto["hidden"] is True

    view = hq.casa.build()
    assert view["people"] == ["person.anna"] and view["states"]["person.anna"]["k"] == "person"
    assert hq.casa.compact("media_player.salotto")["a"]["volume_level"] == 0.3
    task.cancel()


async def test_valves_are_their_own_kind(make_hq):
    hq = make_hq([])
    w, ws, task = await connected()
    hq.casa.ha = hq.watcher = w
    w.states["valve.irrigazione_giardino"] = st("valve.irrigazione_giardino", "closed", friendly_name="Irrigazione", supported_features=3)
    c = hq.casa.compact("valve.irrigazione_giardino")
    assert c["k"] == "valve" and c["a"]["supported_features"] == 3
    task.cancel()


def test_downsample_keeps_numbers_and_the_last_point():
    from hubnex.casa import downsample
    pts = [(f"t{i}", str(i)) for i in range(200)] + [("tx", "unavailable")]
    out = downsample(pts, 48)
    assert len(out) == 48 and out[-1] == ["t199", 199.0] and out[0] == ["t0", 0.0]


async def test_plugs_show_the_power_of_their_device(make_hq):
    hq = make_hq([])
    w, ws, task = await connected()
    hq.casa.ha = hq.watcher = w
    w.states["switch.lavatrice"] = st("switch.lavatrice", "on", friendly_name="Lavatrice")
    w.states["sensor.lavatrice_potenza"] = st("sensor.lavatrice_potenza", "1920", device_class="power", unit_of_measurement="W")
    w.entities["switch.lavatrice"] = {"entity_id": "switch.lavatrice", "device_id": "dev-lav", "area_id": "soggiorno"}
    w.entities["sensor.lavatrice_potenza"] = {"entity_id": "sensor.lavatrice_potenza", "device_id": "dev-lav", "area_id": None}
    view = hq.casa.build()
    assert view["power"]["switch.lavatrice"] == "sensor.lavatrice_potenza"
    assert view["states"]["sensor.lavatrice_potenza"]["s"] == "1920"
    task.cancel()


def test_history_for_the_sensor_charts(settings, make_hq):
    hq = make_hq([])
    asked = []

    class FakeREST:
        enabled = True

        async def history(self, eids, hours=24):
            asked.append((eids, hours))
            return {e: [(f"t{i}", str(20 + i / 10)) for i in range(100)] for e in eids}

        async def close(self):
            pass

    hq.ha = FakeREST()
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w
        client.get("/api/casa")  # what the house shows
        out = client.get("/api/casa/history", params={"e": "light.lampada,sensor.segreto", "hours": 500}).json()
        assert list(out) == ["light.lampada"] and len(out["light.lampada"]) == 48  # only shown entities, downsampled
        assert asked == [(["light.lampada"], 72)]
        client.portal.call(lambda: task.cancel())


def test_cards_composed_in_a_room_and_helpers_set_from_the_dashboard(settings, make_hq):
    hq = make_hq([])
    calls = []

    class FakeREST:
        enabled = True

        async def call_service(self, domain, service, data, by_owner=False):
            calls.append((domain, service, data))
            return []

        async def close(self):
            pass

    hq.ha = FakeREST()
    settings.trusted_proxy = None
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w
        w.states["input_datetime.stufa_accensione"] = st("input_datetime.stufa_accensione", "06:30:00", has_date=False, has_time=True, friendly_name="Stufa accensione")
        w.states["input_datetime.stufa_spegnimento"] = st("input_datetime.stufa_spegnimento", "22:00:00", has_date=False, has_time=True)

        r = client.post("/api/casa/rooms/soggiorno/cards", json={"name": "Stufa", "entities": ["input_datetime.stufa_accensione", "input_datetime.stufa_spegnimento"], "size": "wide", "group": "climate"})
        assert r.json() == {"ok": True, "id": "c1"}
        assert client.post("/api/casa/rooms/soggiorno/cards", json={"name": "X", "entities": ["light.inesistente"]}).status_code == 422
        bad = {"name": "Stufa", "entities": ["input_datetime.stufa_accensione"], "enable": "light.lampada"}
        assert client.post("/api/casa/rooms/soggiorno/cards", json=bad).status_code == 422  # its switch must be in the card
        # a free card: blocks on the grid; its entities are its blocks'
        free = {"name": "Stufa libera", "kind": "free", "color": "warm", "blocks": [
            {"kind": "band", "entity": "input_datetime.stufa_accensione", "entity2": "input_datetime.stufa_spegnimento", "w": 4},
            {"kind": "text", "label": "Inverno", "w": 4},
            {"kind": "ring", "entity": "input_datetime.stufa_accensione", "min": 0, "max": 5},
        ]}
        r = client.post("/api/casa/rooms/soggiorno/cards", json=free)
        assert r.json() == {"ok": True, "id": "c2"}
        assert client.post("/api/casa/rooms/soggiorno/cards", json={**free, "blocks": []}).status_code == 422
        assert client.post("/api/casa/rooms/soggiorno/cards", json={**free, "blocks": [{"kind": "razzo", "entity": "x.y"}]}).status_code == 422
        assert client.post("/api/casa/rooms/soggiorno/cards", json={**free, "blocks": [{"kind": "value", "entity": "light.inesistente"}]}).status_code == 422
        assert client.post("/api/casa/rooms/soggiorno/cards", json={**free, "blocks": [{"kind": "value", "entity": "input_datetime.stufa_accensione", "w": 5}]}).status_code == 422
        # part two: colour rules, a condition, a tap; their entities belong to the card too
        w.states["light.lampada"] = st("light.lampada", "on", friendly_name="Lampada")
        smart = {"name": "Regole", "kind": "free", "blocks": [
            {"kind": "value", "entity": "input_datetime.stufa_accensione", "rules": [{"op": ">", "v": "21", "c": "red"}],
             "show": {"e": "light.lampada", "op": "=", "v": "on"}, "tap": {"do": "ask", "text": "Quanto pellet mi resta?"}},
            {"kind": "ask", "label": "Che tempo fa?"},
            {"kind": "state", "entity": "input_datetime.stufa_spegnimento", "tap": {"do": "toggle", "e": "light.lampada"}},
        ]}
        r = client.post("/api/casa/rooms/soggiorno/cards", json=smart)
        assert r.status_code == 200, r.text
        bad_rule = {**smart, "blocks": [{"kind": "value", "entity": "light.lampada", "rules": [{"op": "~", "v": "1", "c": "red"}]}]}
        assert client.post("/api/casa/rooms/soggiorno/cards", json=bad_rule).status_code == 422
        bad_tap = {**smart, "blocks": [{"kind": "value", "entity": "light.lampada", "tap": {"do": "explode"}}]}
        assert client.post("/api/casa/rooms/soggiorno/cards", json=bad_tap).status_code == 422
        got = next(c for c in next(a for a in client.get("/api/casa").json()["areas"] if a["id"] == "soggiorno")["cards"] if c["id"] == r.json()["id"])
        assert got["entities"] == ["input_datetime.stufa_accensione", "light.lampada", "input_datetime.stufa_spegnimento"]
        assert got["blocks"][0]["rules"] == [{"op": ">", "v": "21", "c": "red"}] and got["blocks"][0]["show"]["e"] == "light.lampada"
        assert "rules" not in got["blocks"][1] and got["blocks"][1]["label"] == "Che tempo fa?"
        client.post(f"/api/casa/rooms/soggiorno/cards/{r.json()['id']}/remove")
        view = client.get("/api/casa").json()
        sogg = next(a for a in view["areas"] if a["id"] == "soggiorno")
        card = sogg["cards"][1]
        assert card["kind"] == "free" and card["color"] == "warm" and len(card["blocks"]) == 3
        assert card["entities"] == ["input_datetime.stufa_accensione", "input_datetime.stufa_spegnimento"]
        assert card["blocks"][2] == {"kind": "ring", "entity": "input_datetime.stufa_accensione", "entity2": "", "label": "", "w": 1, "h": 1, "min": 0.0, "max": 5.0}
        assert sogg["cards"][0]["name"] == "Stufa" and sogg["cards"][0]["group"] == "climate" and sogg["order"] == []
        assert view["states"]["input_datetime.stufa_accensione"]["k"] == "datetime"  # sent although in no area
        assert view["states"]["input_datetime.stufa_accensione"]["a"]["has_time"] is True

        client.post("/api/casa/rooms/soggiorno/order", json={"items": ["light.lampada", "card:c1"]})
        client.post("/api/casa/entities/light.lampada/display", json={"name": "Lampada grande", "size": "wide"})
        view = client.get("/api/casa").json()
        assert next(a for a in view["areas"] if a["id"] == "soggiorno")["order"] == ["light.lampada", "card:c1"]
        assert view["states"]["light.lampada"]["n"] == "Lampada grande" and view["sizes"] == {"light.lampada": "wide"}
        client.post("/api/casa/entities/light.lampada/display", json={"name": None})  # back to Home Assistant's name
        w.states["sensor.lux"] = st("sensor.lux", "37", device_class="illuminance", unit_of_measurement="lx")
        client.post("/api/casa/entities/sensor.lux/display", json={"chart": False})
        assert client.get("/api/casa").json()["nochart"] == ["sensor.lux"]
        client.post("/api/casa/entities/sensor.lux/display", json={"chart": True})
        assert client.get("/api/casa").json()["nochart"] == []
        r = client.post("/api/casa/rooms/soggiorno/cards", json={"name": "Luce", "entities": ["sensor.lux"], "nochart": ["sensor.lux", "light.altro"]})
        luce = next(c for c in next(a for a in client.get("/api/casa").json()["areas"] if a["id"] == "soggiorno")["cards"] if c["id"] == r.json()["id"])
        assert luce["nochart"] == ["sensor.lux"]  # only the card's own entities
        assert client.get("/api/casa").json()["sizes"] == {"light.lampada": "wide"}

        client.post("/api/casa/call", json={"domain": "input_datetime", "service": "set_datetime", "data": {"entity_id": "input_datetime.stufa_accensione", "time": "07:00:00"}})
        assert calls[-1] == ("input_datetime", "set_datetime", {"entity_id": "input_datetime.stufa_accensione", "time": "07:00:00"})
        client.post("/api/casa/rooms/soggiorno/cards/c1/remove")
        assert [c["id"] for c in next(a for a in client.get("/api/casa").json()["areas"] if a["id"] == "soggiorno")["cards"]] == ["c2", "c3"]
        client.portal.call(lambda: task.cancel())


def test_energy_panel_config_and_live_data(settings, make_hq):
    hq = make_hq([])

    class FakeREST:
        enabled = True

        async def history(self, eids, hours=24):
            return {eids[0]: [("2000-01-01T00:00:00+00:00", "1000")]}  # 1 kW since long before midnight

        async def close(self):
            pass

    hq.ha = FakeREST()
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w
        w.states["sensor.f1"] = st("sensor.f1", "52.6", unit_of_measurement="kWh", last_period="70", last_reset="2026-09-01T00:00:00+02:00", meter_period="bimonthly")
        w.states["sensor.w"] = st("sensor.w", "560", unit_of_measurement="W")
        cfg = client.post("/api/casa/energy/config", json={"views": ["bill", "reactor"], "band_mode": "arera", "bands": {"F1": "sensor.f1", "F2": "sensor.nessuno"}, "power": "sensor.w", "readouts": ["sensor.nessuno"]}).json()
        assert cfg["bands"] == {"F1": "sensor.f1"} and cfg["readouts"] == [] and cfg["views"] == ["bill", "reactor"]  # unknown entities dropped
        view = client.get("/api/casa").json()
        assert view["energy_panel"]["power"] == "sensor.w" and view["states"]["sensor.f1"]["a"]["last_period"] == "70"
        live = client.get("/api/casa/energy").json()
        assert live["band"]["name"] in ("F1", "F2", "F3") and len(live["band"]["until"]) == 5
        assert sum(live["day"]["kwh"].values()) > 0 and live["day"]["points"][0][1] == 1000.0
        client.portal.call(lambda: task.cancel())


def test_vacuum_map_is_found_on_the_same_device():
    from types import SimpleNamespace as NS

    from hubnex.casa import Casa

    ha = NS(states={"vacuum.robot": {}, "image.robot_mappa": {}, "camera.ingresso": {}},
            entities={"vacuum.robot": {"device_id": "d1"}, "image.robot_mappa": {"device_id": "d1"}, "camera.ingresso": {"device_id": "d2"}})
    casa = Casa.__new__(Casa)
    casa.ha = ha
    assert casa.vacuum_map("vacuum.robot") == "image.robot_mappa"
    # no device: a map whose name says so
    ha.entities = {}
    ha.states = {"vacuum.roborock_s8": {}, "camera.roborock_map": {}, "camera.ingresso": {}}
    assert casa.vacuum_map("vacuum.roborock_s8") == "camera.roborock_map"
    ha.states = {"vacuum.robot": {}, "camera.ingresso": {}}
    assert casa.vacuum_map("vacuum.robot") is None


async def test_the_forecast_comes_from_home_assistant_service():
    import json as _json

    import httpx

    from hubnex.integrations.homeassistant import HomeAssistant

    seen = {}

    def handle(req):
        seen.update(url=str(req.url), body=_json.loads(req.content))
        return httpx.Response(200, json={"changed_states": [], "service_response": {
            "weather.casa": {"forecast": [{"datetime": "2026-11-08T00:00:00Z", "condition": "rainy", "temperature": 14, "templow": 9}]}}})

    ha = HomeAssistant("http://ha:8123", "tok")
    ha._client = httpx.AsyncClient(base_url="http://ha:8123/api", transport=httpx.MockTransport(handle))
    days = await ha.forecast("weather.casa")
    assert days[0]["condition"] == "rainy"
    assert seen["url"].endswith("/api/services/weather/get_forecasts?return_response")
    assert seen["body"] == {"entity_id": "weather.casa", "type": "daily"}


def test_stock_pace_from_the_history():
    from datetime import datetime, timedelta, timezone

    from hubnex.main import stock_stats

    now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
    day = lambda d: (now - timedelta(days=d)).isoformat()  # noqa: E731
    pts = [(day(10), "20"), (day(8), "17"), (day(6), "14"), (day(4), "26"), (day(2), "23"), (day(0), "20"), (day(0), "unavailable")]
    out = stock_stats(pts, now)
    assert out["per_day"] == 1.2  # 12 used in 10 days, the delivery doesn't count
    assert out["days_left"] == 16
    assert out["last_delivery"] == day(4)
    assert stock_stats([(day(1), "5")], now) == {"per_day": None, "days_left": None, "last_delivery": None}


def test_counters_are_stocks_by_name_and_any_entity_can_be_searched():
    from types import SimpleNamespace as NS

    from hubnex.casa import Casa

    casa = Casa.__new__(Casa)
    casa.adjust = {"kind": {}, "names": {}, "extra": {}, "hidden": {}}
    states = {f"automation.regola_{i}": {"state": "on", "attributes": {}} for i in range(120)}
    states["counter.carico_pellet"] = {"state": "12", "attributes": {"friendly_name": "Carico pellet", "minimum": 0}}
    states["counter.visite"] = {"state": "3", "attributes": {"friendly_name": "Visite"}}
    casa.ha = NS(states=states, entities={}, areas={}, area_of=lambda e: None)
    assert casa.compact("counter.carico_pellet")["k"] == "stock"
    assert casa.compact("counter.visite")["k"] == "number"
    found = casa.candidates("")
    assert len(found) == 122, "no limit at 60: every entity can be added to a room"


def test_jarvis_composes_a_free_card_and_cards_travel_as_text(settings, make_hq):
    import json as _json

    draft = {"name": "Soggiorno", "color": "warm", "blocks": [
        {"kind": "toggle", "entity": "light.lampada", "label": "", "w": 1, "h": 1, "rules": [{"op": "=", "v": "on", "c": "warm"}]},
        {"kind": "toggle", "entity": "light.inventata", "label": "", "w": 1, "h": 1},  # made up: left out
        {"kind": "ask", "entity": "", "label": "Che luci ho acceso?", "w": 2, "h": 1},
        {"kind": "state", "entity": "switch.irrigazione", "label": "", "w": 2, "h": 1, "show": {"e": "sensor.nessuno", "op": "=", "v": "on"}},
    ]}
    hq = make_hq([response([text_block(_json.dumps(draft))], "end_turn")])
    settings.trusted_proxy = None
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        w, ws, task = client.portal.call(connected)
        hq.casa.ha = hq.watcher = w
        r = client.post("/api/casa/rooms/soggiorno/cards/draft", json={"text": "le luci del soggiorno e l'irrigazione"})
        assert r.status_code == 200, r.text
        got = r.json()
        assert got["name"] == "Soggiorno" and got["color"] == "warm" and got["dropped"] == 1
        assert [b["entity"] for b in got["blocks"]] == ["light.lampada", "", "switch.irrigazione"]
        assert "show" not in got["blocks"][2]  # its condition named an entity that doesn't exist
        assert set(got["states"]) == {"light.lampada", "switch.irrigazione"} and got["states"]["light.lampada"]["k"] == "light"
        req = hq.client.requests[0]
        assert "output_config" in req and req["output_config"]["format"]["type"] == "json_schema"
        prompt = req["messages"][0]["content"]
        assert "light.lampada | Lampada da terra | light" in prompt and "le luci del soggiorno" in prompt
        assert prompt.index("light.lampada") < prompt.index("light.lampadario")  # the room first
        assert client.post("/api/casa/rooms/nessuna/cards/draft", json={"text": "una card"}).status_code == 404

        # export from one house, import into another: missing entities wait to be chosen
        shared = {"hubnex_card": 1, "name": "Da un amico", "color": "cool", "blocks": [
            {"kind": "toggle", "entity": "light.lampada", "w": 1, "h": 1},
            {"kind": "value", "entity": "sensor.casa_amico", "w": 2, "h": 1, "tap": {"do": "toggle", "e": "light.amico"}},
            {"kind": "boom"},
        ]}
        got = client.post("/api/casa/cards/import", json=shared).json()
        assert got["missing"] == 1 and got["dropped"] == 1
        assert got["blocks"][1]["entity"] == "" and got["blocks"][1]["tap"]["e"] == ""
        assert got["style"] is None  # not given: the editor keeps its own (clean, for a new card)
        assert client.post("/api/casa/cards/import", json={**shared, "style": "flat"}).json()["style"] == "flat"
        assert client.post("/api/casa/cards/import", json={"name": "x"}).status_code == 422
        client.portal.call(lambda: task.cancel())
