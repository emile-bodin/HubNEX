"""brAIn's Home Assistant tools, answered inside HubNEX.

`InProcessServer` has the interface of integrations.mcp.MCPClient (list_tools, call_tool,
instructions), so connectors.py offers it as the built-in connector "casa" with everything a
connector has: which agents get it, the owner's confirmation for tools that change the house,
the status on the dashboard. Nothing goes over a pipe or the network: tools/list and tools/call
are function calls into the ported module (brain_server.py).

The ported module is synchronous, as it is in brAIn. Its tools run on one worker thread of their
own (brAIn's server is single-threaded; its small caches assume it), and reach Home Assistant
through HubNEX's own connections: the REST client and the WebSocket HubNEX already holds — the
three functions brAIn used for that, and its panel calls, are replaced when the module loads.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from hubnex.context import ORIGIN, VOICE
from hubnex.integrations.mcp import tool_result
from hubnex.mcp_server import catalog, context

if TYPE_CHECKING:
    from hubnex.hq import HQ

log = logging.getLogger("hubnex.mcp_server")
TIMEOUT = 45  # seconds a tool may wait on Home Assistant
NOT_HERE = "not available in HubNEX (it needs brAIn's own panel)"


class InProcessServer:
    """The ported server, called directly. One per HQ."""

    def __init__(self, hq: "HQ"):
        self.hq = hq
        self.url = "inprocess://casa"
        self.server_name = "casa"
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hubnex-casa")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mod = None

    # ------------------------------------------------------------------ what MCPClient has
    @property
    def instructions(self) -> str:
        return catalog.VOICE_INSTRUCTIONS if VOICE.get() else catalog.INSTRUCTIONS

    async def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    async def list_tools(self) -> list[dict]:
        """The tools of the groups switched on in the add-on page, minus the excluded ones, with
        HubNEX's descriptions and whether each one only reads."""
        mod = self._module()
        s = self.hq.settings
        names = set(catalog.tools_in(s.ha_mcp_groups, s.ha_mcp_exclude_tools))
        out = []
        for spec in mod.TOOLS:
            if spec["name"] not in names:
                continue
            out.append({
                "name": spec["name"],
                "description": catalog.clean_description(spec.get("description", "")),
                "inputSchema": spec.get("inputSchema") or {"type": "object", "properties": {}},
                "annotations": {"readOnlyHint": spec["name"] not in catalog.WRITE_TOOLS,
                                "title": spec["name"].replace("_", " ")},
            })
        return out

    async def call_tool(self, name: str, arguments: dict, images: bool = True, max_chars: int = 15_000,
                        agent_id: str | None = None) -> tuple[str | list[dict], bool]:
        if name not in catalog.ALL_TOOLS:
            return f"Unknown tool: {name}", True
        if name in catalog.WRITE_TOOLS and ORIGIN.get() != "owner":
            # HubNEX's rule for the house: routines and events look and report, only the owner acts.
            return ("Refused: only the owner's own requests may change the house; a routine or an "
                    "event can look and report."), True
        mod = self._module()
        self._loop = asyncio.get_running_loop()
        values = self.call_context(agent_id)
        ctx = contextvars.copy_context()  # the worker sees ORIGIN, the chat… of this call
        try:
            result = await asyncio.wait_for(
                self._loop.run_in_executor(self._pool, ctx.run, self._run, mod, values, name, arguments or {}),
                TIMEOUT + 15,
            )
        except asyncio.TimeoutError:
            return f"{name}: Home Assistant did not answer in time", True
        return tool_result(mod.build_tool_response(result), images, max_chars)

    # ------------------------------------------------------------------ per call
    def call_context(self, agent_id: str | None = None) -> dict:
        """What brAIn read from its environment, for this call (see context.py)."""
        s = self.hq.settings
        voice = bool(VOICE.get())
        origin = ORIGIN.get()
        channel = "voice" if voice else ("chat" if origin == "owner" else "task")
        denied = {x.lower() for x in s.ha_blocked_services}
        if voice:
            denied |= {x.lower() for x in s.ha_voice_blocked_services}
        return {
            "env": {"BRAIN_CHANNEL": channel},
            "exposed_only": voice and s.ha_voice_exposed_only,
            "denied_services": sorted(denied),
            "protected_entities": list(s.ha_protected_entities),
            "agent_id": agent_id,
        }

    @staticmethod
    def _run(mod, values: dict, name: str, arguments: dict):
        context.CALL.set(values)
        return mod.handle_tool_call(name, arguments)

    # ------------------------------------------------------------------ the ported module
    def _module(self):
        if self._mod is not None:
            return self._mod
        data = Path(self.hq.settings.db_path).resolve().parent
        context.STATIC["BRAIN_EXPOSED_CACHE"] = str(data / "brain_exposed.json")
        from hubnex.mcp_server import brain_server as mod

        mod.ha_api_request = self.ha_api_request
        mod.ha_api_request_raw = self.ha_api_request_raw
        mod._ws_command = self.ws_command
        mod._panel_get = lambda *a, **k: {"error": NOT_HERE}
        mod._panel_send = lambda *a, **k: {"error": NOT_HERE}
        mod.yolo_mode = lambda: False  # brAIn's switch that stands every rule down: never here
        mod.record_action = self.record_action
        self._mod = mod
        return mod

    def _wait(self, coro, timeout: float = TIMEOUT):
        """Run a coroutine on HubNEX's event loop from the worker thread and wait for it."""
        if self._loop is None:
            raise RuntimeError("no event loop")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    # --- the three ways brAIn reached Home Assistant -------------------------
    def ha_api_request(self, endpoint, method="GET", data=None, accept=None):
        """brAIn's REST helper: parsed JSON (or text), {"error": …} on failure. Never raises."""
        try:
            if endpoint.startswith("/api/"):
                return self._wait(self._rest(method, endpoint[4:], data, accept))
            if endpoint.startswith("/"):
                return self._supervisor(endpoint, method, data)
            return self._wait(self._rest(method, "/" + endpoint, data, accept))
        except Exception as exc:  # noqa: BLE001 — brAIn's contract: an error dict
            return {"error": str(exc) or exc.__class__.__name__}

    async def _rest(self, method: str, path: str, data, accept):
        if method == "GET" and self.hq.watcher.ready.is_set():
            states = self.hq.watcher.states  # already in memory: no round trip
            if path == "/states":
                return list(states.values())
            if path.startswith("/states/") and path[8:] in states:
                return states[path[8:]]
        headers = {"Accept": accept} if accept else {}
        r = await self.hq.ha._client.request(method, path, json=data if data else None, headers=headers,
                                             timeout=TIMEOUT)
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}: {r.reason_phrase}", "details": r.text[:2000]}
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text  # some endpoints (the error log) answer in plain text

    def ha_api_request_raw(self, endpoint):
        """Raw bytes of a GET (camera frames). Raises on failure, as brAIn's did."""
        path = endpoint[4:] if endpoint.startswith("/api/") else "/" + endpoint.lstrip("/")

        async def get():
            r = await self.hq.ha._client.get(path, timeout=TIMEOUT)
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.reason_phrase}")
            return r.content

        return self._wait(get())

    def ws_command(self, payload, timeout=15):
        """One command over HubNEX's own WebSocket to Home Assistant."""
        if self.hq.watcher._ws is None:
            return {"error": "Home Assistant's WebSocket is not connected"}
        try:
            return self._wait(self.hq.watcher._command(dict(payload), timeout), timeout + 5)
        except TimeoutError:
            raise
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc) or exc.__class__.__name__}

    @staticmethod
    def _supervisor(endpoint: str, method: str, data):
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return {"error": "the Supervisor is only reachable when HubNEX runs as a Home Assistant add-on"}
        r = httpx.request(method, f"http://supervisor{endpoint}", json=data or None, timeout=30,
                          headers={"Authorization": f"Bearer {token}"})
        if r.status_code >= 400:
            return {"error": f"HTTP {r.status_code}", "details": r.text[:2000]}
        try:
            return r.json()
        except ValueError:
            return r.text

    # --- what HubNEX did in the house ---------------------------------------
    def record_action(self, domain, service, data, extra=()):
        """brAIn's ledger, in HubNEX's database and activity feed. Never raises: accounting
        must not fail the call it accounts for."""
        try:
            entities = list(self._mod._call_entities(data, extra)) if self._mod else []
            values = context.CALL.get()
            agent = values.get("agent_id")
            channel = (values.get("env") or {}).get("BRAIN_CHANNEL")
            asyncio.run_coroutine_threadsafe(
                self._record(f"{domain}.{service}", entities, data, agent, channel), self._loop)
        except Exception:  # noqa: BLE001
            log.debug("could not record a Home Assistant action", exc_info=True)

    async def _record(self, service: str, entities: list[str], data: Any, agent: str | None,
                      channel: str | None) -> None:
        hq = self.hq
        await hq.store.ha_action_add(service, entities, data, agent_id=agent, channel=channel)
        who = hq.agent_name(agent) if agent else hq.org.boss_name
        await hq.log("ha", f"{who}: {service} {', '.join(entities)}".strip(), agent)
        hq.emit({"type": "ha_action", "service": service, "entities": entities, "ts": time.time()})
