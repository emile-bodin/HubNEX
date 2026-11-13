"""Live view of Home Assistant over its WebSocket API: areas, devices, entities and states.

The REST API has no registries (which area an entity belongs to) and no push, so the house
view keeps one WebSocket open: it loads the registries and all states, then follows
`state_changed` and the registry-updated events. It also moves an entity to another area.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
from typing import Any, Awaitable, Callable

import websockets
from hubnex.i18n import lang, tr

log = logging.getLogger(__name__)

REGISTRY_EVENTS = ("area_registry_updated", "entity_registry_updated", "device_registry_updated", "floor_registry_updated")
APP_ACTION = "mobile_app_notification_action"  # a button pressed on a notification of the companion app
# Called with ("state", entity_id, new_state_or_None), ("registry", None, None) or
# ("app_action", action_id, event_data).
OnEvent = Callable[[str, str | None, dict | None], Awaitable[None]]


class HAWatcherError(Exception):
    pass


def websocket_url(ha_url: str) -> str:
    """http://supervisor/core -> ws://supervisor/core/websocket (add-on proxy);
    http://host:8123 -> ws://host:8123/api/websocket (Home Assistant directly)."""
    base = ha_url.rstrip("/")
    ws = "wss" + base[5:] if base.startswith("https") else "ws" + base[4:]
    return f"{ws}/websocket" if base.endswith("/core") else f"{ws}/api/websocket"


class HAWatcher:
    def __init__(self, ha_url: str, token: str, on_event: OnEvent | None = None, connect=None):
        self.url = websocket_url(ha_url) if ha_url else ""
        self.token = token
        self.on_event = on_event
        self._connect = connect or (lambda url: websockets.connect(url, max_size=None, ping_interval=30))
        self.areas: dict[str, dict] = {}
        self.language: str | None = None
        self.time_zone: str | None = None  # Home Assistant's own, e.g. "Europe/Rome"
        self.on_language = None  # called with Home Assistant's language once it is known
        self.floors: dict[str, dict] = {}
        self.devices: dict[str, dict] = {}
        self.entities: dict[str, dict] = {}  # entity registry, by entity_id
        self.states: dict[str, dict] = {}
        self.ready = asyncio.Event()
        self._ws = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._reload_task: asyncio.Task | None = None
        self._admins: dict[str, bool] = {}  # user id -> administrator
        self._admins_at = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    # ------------------------------------------------------------------ connection
    async def run(self) -> None:
        delay = 2
        while True:
            try:
                await self._session()
                delay = 2
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # network, auth, HA restarting...
                log.warning("Home Assistant WebSocket: %s (riprovo tra %ss)", exc, delay)
            self.ready.clear()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    async def _session(self) -> None:
        async with self._connect(self.url) as ws:
            msg = json.loads(await ws.recv())
            if msg.get("type") != "auth_required":
                raise HAWatcherError(tr("risposta inattesa: {a}", a=msg))
            await ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            msg = json.loads(await ws.recv())
            if msg.get("type") != "auth_ok":
                raise HAWatcherError(tr("autenticazione rifiutata"))
            self._ws = ws
            reader = asyncio.create_task(self._read(ws))
            try:
                await self._command({"type": "subscribe_events", "event_type": "state_changed"})
                for ev in (*REGISTRY_EVENTS, APP_ACTION):
                    await self._command({"type": "subscribe_events", "event_type": ev})
                await self._load()
                self.ready.set()
                await self._notify("registry", None, None)
                await reader
            finally:
                reader.cancel()
                self._ws = None
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(HAWatcherError(tr("connessione chiusa")))
                self._pending.clear()

    async def _read(self, ws) -> None:
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get("type") == "result":
                fut = self._pending.pop(msg.get("id"), None)
                if fut and not fut.done():
                    if msg.get("success"):
                        fut.set_result(msg.get("result"))
                    else:
                        fut.set_exception(HAWatcherError((msg.get("error") or {}).get("message", "errore")))
            elif msg.get("type") == "event":
                await self._event(msg.get("event") or {})

    async def _command(self, payload: dict, timeout: float = 30) -> Any:
        if self._ws is None:
            raise HAWatcherError(tr("Home Assistant non collegato"))
        mid = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await self._ws.send(json.dumps({"id": mid, **payload}))
        return await asyncio.wait_for(fut, timeout)

    # ------------------------------------------------------------------ data
    async def _load(self) -> None:
        areas = await self._command({"type": "config/area_registry/list"})
        try:
            floors = await self._command({"type": "config/floor_registry/list"})
        except HAWatcherError:  # older Home Assistant: no floors
            floors = []
        devices = await self._command({"type": "config/device_registry/list"})
        entities = await self._command({"type": "config/entity_registry/list"})
        states = await self._command({"type": "get_states"})
        self.areas = {a["area_id"]: a for a in areas}
        self.floors = {f["floor_id"]: f for f in floors}
        self.devices = {d["id"]: d for d in devices}
        self.entities = {e["entity_id"]: e for e in entities}
        self.states = {s["entity_id"]: s for s in states}
        await self._load_aliases()
        try:  # Home Assistant's language: the add-on speaks it unless told otherwise
            ha_config = (await self._command({"type": "get_config"})) or {}
            self.language = ha_config.get("language")
            self.time_zone = ha_config.get("time_zone") or self.time_zone
        except HAWatcherError:
            self.language = None
        if self.language and self.on_language:
            self.on_language(self.language)

    async def _load_aliases(self) -> None:
        """The aliases set in Home Assistant (entity settings → Aliases): the list above leaves
        them out, the full entries have them."""
        if not self.entities:
            return
        try:
            full = await self._command({"type": "config/entity_registry/get_entries", "entity_ids": list(self.entities)})
        except (HAWatcherError, asyncio.TimeoutError) as exc:  # older Home Assistant
            log.debug("alias non disponibili: %s", exc)
            return
        for eid, entry in (full or {}).items():
            aliases = [a.strip() for a in (entry or {}).get("aliases") or [] if isinstance(a, str) and a.strip()]
            if aliases and eid in self.entities:
                self.entities[eid]["aliases"] = aliases

    async def _event(self, event: dict) -> None:
        etype = event.get("event_type")
        if etype == "state_changed":
            data = event.get("data") or {}
            eid, new = data.get("entity_id"), data.get("new_state")
            if not eid:
                return
            if new is None:
                self.states.pop(eid, None)
            else:
                self.states[eid] = new
            await self._notify("state", eid, new)
        elif etype == APP_ACTION:
            data = event.get("data") or {}
            if data.get("action"):
                await self._notify("app_action", data["action"], data)
        elif etype in REGISTRY_EVENTS:
            # Edits often come in bursts (renaming a device touches all its entities).
            if self._reload_task is None or self._reload_task.done():
                self._reload_task = asyncio.create_task(self._reload_soon())

    async def _reload_soon(self) -> None:
        await asyncio.sleep(1)
        try:
            await self._load()
        except Exception as exc:
            log.warning("ricarico dei registri fallito: %s", exc)
            return
        await self._notify("registry", None, None)

    async def _notify(self, kind: str, eid: str | None, state: dict | None) -> None:
        if self.on_event:
            try:
                await self.on_event(kind, eid, state)
            except Exception:
                log.exception("HA event handler failed")

    # ------------------------------------------------------------------ queries and changes
    async def phones(self) -> list[dict]:
        """The companion apps that can receive notifications: notify.mobile_app_<device>."""
        try:
            services = await self._command({"type": "get_services"}, timeout=10)
        except (HAWatcherError, asyncio.TimeoutError):
            return []
        out = []
        for name in sorted((services or {}).get("notify") or {}):
            if name.startswith("mobile_app_"):
                dev = next((d for d in self.devices.values() if (d.get("name_by_user") or d.get("name") or "").lower().replace(" ", "_").replace("-", "_") == name[11:]), None)
                out.append({"service": name, "name": (dev or {}).get("name_by_user") or (dev or {}).get("name") or name[11:].replace("_", " ")})
        return out

    async def statistics(
        self, statistic_ids: list[str], start: str, end: str, period: str = "hour",
        types: tuple[str, ...] = ("mean", "min", "max", "sum", "change"),
    ) -> dict[str, list[dict]]:
        """Long-term statistics from the recorder (read-only): {statistic_id: [rows]}."""
        return await self._command({
            "type": "recorder/statistics_during_period", "start_time": start, "end_time": end,
            "statistic_ids": statistic_ids, "period": period, "types": list(types),
        }) or {}

    def area_of(self, entity_id: str) -> str | None:
        """The entity's own area, or else its device's (that is what Home Assistant shows)."""
        reg = self.entities.get(entity_id)
        if not reg:
            return None
        if reg.get("area_id"):
            return reg["area_id"]
        dev = self.devices.get(reg.get("device_id") or "")
        return dev.get("area_id") if dev else None

    async def tts_voice(self, engine: str, wanted: str = "") -> tuple[str | None, str | None]:
        """The engine's variant of the add-on's language and the voice id for
        a TTS engine; `wanted` is the voice's name as people see it ("Rinaldo") or its id.
        Unknown voice: an error listing the ones there are."""
        info = await self._command({"type": "tts/engine/get", "engine_id": engine}) or {}
        langs = (info.get("provider") or {}).get("supported_languages") or []
        want = lang()
        language = next((x for x in langs if x.lower().replace("_", "-").split("-")[0] == want), None)
        if not wanted:
            return language, None
        if not language:
            raise HAWatcherError(tr("{a} non supporta l'olandese", a=engine) if want == "nl"
                                 else tr("{a} non supporta l'inglese", a=engine))
        res = await self._command({"type": "tts/engine/voices", "engine_id": engine, "language": language}) or {}
        voices = res.get("voices") or []
        w = wanted.casefold()
        for test in (lambda v: w in (v["voice_id"].casefold(), v["name"].casefold()),
                     lambda v: v["name"].casefold().startswith(w) or v["voice_id"].casefold().startswith(w),
                     lambda v: w in v["name"].casefold() or w in v["voice_id"].casefold()):
            hit = next((v for v in voices if test(v)), None)
            if hit:
                return language, hit["voice_id"]
        names = ", ".join(v["name"] for v in voices[:30]) or "nessuna"
        raise HAWatcherError(tr("voce '{a}' non trovata in {b} ({c}). Disponibili: {d}", a=wanted, b=engine, c=language, d=names))

    async def is_admin(self, user_id: str) -> bool:
        """Whether a Home Assistant user is an administrator (owner or in the admin group)."""
        if user_id not in self._admins or time.monotonic() - self._admins_at > 300:
            users = await self._command({"type": "config/auth/list"})
            self._admins = {
                u["id"]: bool(u.get("is_owner")) or "system-admin" in (u.get("group_ids") or []) for u in users or []
            }
            self._admins_at = time.monotonic()
        return self._admins.get(user_id, False)

    async def set_area(self, entity_id: str, area_id: str | None) -> None:
        if entity_id not in self.entities:
            raise HAWatcherError(
                f"{entity_id} non ha un ID univoco in Home Assistant: l'area non si può assegnare, "
                "aggiungila solo alla plancia"
            )
        result = await self._command({"type": "config/entity_registry/update", "entity_id": entity_id, "area_id": area_id})
        entry = (result or {}).get("entity_entry") if isinstance(result, dict) else None
        self.entities[entity_id] = entry or {**self.entities[entity_id], "area_id": area_id}
