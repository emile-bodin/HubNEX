"""Connectors: the programs of your work (management software, calendar, CRM…) through MCP.

Each connector in agents.yaml (or on the add-on page, mcp_connectors) is an MCP server. Its tools
are offered to the agents listed for it, named "<connector>__<tool>". Tools that only read run
freely; tools that change data become a pending action that runs only after the owner's ✅ (see
actions.py).

One connector is built in: "casa", Home Assistant through the tools ported from brAIn's MCP
server (mcp_server/), answered inside HubNEX. It is on when Home Assistant is configured and
ha_mcp_enabled is, with the groups, agents and confirmations of the add-on page. An agent's
`ha_mcp:` in agents.yaml narrows the groups it gets (Sentinel: read and camera, no control).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hubnex.config import ConnectorSpec, _connectors
from hubnex.integrations.mcp import MCPClient, MCPError
from hubnex.i18n import tr

if TYPE_CHECKING:
    from hubnex.hq import HQ

log = logging.getLogger("hubnex.connectors")
REFRESH_SECONDS = 15 * 60
# Without annotations from the server, these names are taken as read-only.
READ_PREFIXES = ("get", "list", "search", "read", "find", "query", "fetch", "count", "describe", "lookup", "show", "cerca", "leggi", "elenca")
CASA = "casa"
SEARCH_TOOL = "mcp_search_tools"
# With tool search on, these are offered at once; the rest are found with SEARCH_TOOL.
ALWAYS_LOADED = {"get_entity_state", "get_all_states"}


@dataclass
class ConnectorTool:
    connector: str
    name: str  # as the server calls it
    title: str
    description: str
    schema: dict
    confirm: bool
    read_only: bool = False

    @property
    def full_name(self) -> str:
        return tool_name(self.connector, self.name)


@dataclass
class SearchTool:
    """The one tool standing in for the connector tools not loaded yet (mcp_tool_search):
    finding some adds them to the tools of the running turn."""

    defs: list[dict]  # the turn's tool definitions: found tools are appended here
    hidden: dict[str, ConnectorTool]
    extra: dict  # the turn's connector tools by name: found tools become callable


@dataclass
class Connector:
    spec: ConnectorSpec
    client: Any  # MCPClient, or the built-in InProcessServer
    tools: dict[str, ConnectorTool] = field(default_factory=dict)  # by full name
    loaded: float = 0.0
    error: str | None = None
    builtin: bool = False


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "mcp"


def tool_name(connector: str, tool: str) -> str:
    return f"{slug(connector)}__{re.sub(r'[^A-Za-z0-9_-]', '_', tool)}"[:64]


def read_only(tool: dict) -> bool:
    hints = tool.get("annotations") or {}
    if hints.get("readOnlyHint") is True:
        return True
    if hints.get("readOnlyHint") is False or hints.get("destructiveHint") is True:
        return False
    return tool.get("name", "").lower().startswith(READ_PREFIXES)


def needs_confirmation(spec: ConnectorSpec, tool: dict) -> bool:
    name = tool.get("name", "")
    if spec.confirm == "never" or name in spec.free:
        return False
    if spec.confirm == "always" or name in spec.always_confirm:
        return True
    return not read_only(tool)


def summarize(tool: ConnectorTool, args: dict) -> str:
    lines = [f"{tool.connector}: {tool.title}"]
    for k, v in args.items():
        value = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        lines.append(f"• {k}: {value[:300]}")
    return "\n".join(lines)


def _csv(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [x.strip() for x in str(value or "").replace(";", ",").split(",") if x.strip()]


def page_connectors(raw: list[dict]) -> list[ConnectorSpec]:
    """Connectors from the add-on page: the same fields as agents.yaml, lists as comma text."""
    out = []
    for c in raw or []:
        if not isinstance(c, dict) or not c.get("name") or not c.get("url"):
            continue
        item = dict(c)
        for key in ("agents", "free", "always_confirm", "tools", "exclude"):
            if key in item:
                item[key] = _csv(item[key]) or None
        if not item.get("agents"):
            item.pop("agents", None)
        item["confirm"] = item.get("confirm") or "writes"
        try:
            out.extend(_connectors([item]))
        except ValueError as exc:
            log.warning("add-on page connector skipped: %s", exc)
    return out


class Connectors:
    def __init__(self, hq: "HQ", specs: list[ConnectorSpec], transport=None):
        self.hq = hq
        merged = {slug(s.name): s for s in specs}
        for s in page_connectors(getattr(hq.settings, "mcp_connectors", [])):
            merged[slug(s.name)] = s  # the add-on page wins over agents.yaml
        self.items: dict[str, Connector] = {
            key: Connector(s, MCPClient(s.url, s.headers(), transport=transport)) for key, s in merged.items()
        }
        self._add_builtin()
        hq.actions.executors["mcp"] = self._run_confirmed

    def _add_builtin(self) -> None:
        s = self.hq.settings
        if not (s.ha_mcp_enabled and self.hq.ha.enabled) or CASA in self.items:
            return
        from hubnex.mcp_server.bridge import InProcessServer

        spec = ConnectorSpec(
            name=CASA, url="inprocess://casa", agents=s.ha_mcp_agents, confirm=s.ha_mcp_confirm,
            free=sorted(s.ha_mcp_free_tools),
        )
        self.items[CASA] = Connector(spec, InProcessServer(self.hq), builtin=True)

    @property
    def enabled(self) -> bool:
        return bool(self.items)

    def has_casa(self, agent_id: str) -> bool:
        c = self.items.get(CASA)
        return bool(c and self._allows(c, agent_id))

    def _casa_groups(self, agent_id: str) -> set[str] | None:
        """The casa groups this agent's `ha_mcp:` keeps; None = all the page switched on."""
        groups = self.hq.org.ha_mcp(agent_id)
        return None if groups is None else set(groups) & set(self.hq.settings.ha_mcp_groups)

    def _allows(self, c: Connector, agent_id: str) -> bool:
        if not c.spec.allows(agent_id):
            return False
        return not c.builtin or self._casa_groups(agent_id) != set()

    def _agent_tools(self, c: Connector, agent_id: str) -> dict[str, ConnectorTool]:
        groups = self._casa_groups(agent_id) if c.builtin else None
        if groups is None:
            return c.tools
        from hubnex.mcp_server.catalog import GROUP_OF

        return {k: t for k, t in c.tools.items() if GROUP_OF.get(t.name) in groups}

    async def close(self) -> None:
        for c in self.items.values():
            await c.client.close()

    async def _load(self, c: Connector) -> None:
        if c.loaded and time.monotonic() - c.loaded < REFRESH_SECONDS:
            return
        try:
            raw = await c.client.list_tools()
        except MCPError as exc:
            if c.error != str(exc):
                await self.hq.log("error", f"Connettore {c.spec.name}: {exc}")
            c.error, c.loaded = str(exc), time.monotonic() - REFRESH_SECONDS + 60  # retry in a minute
            return
        except Exception as exc:  # the built-in one: never let a bug take the turn down
            log.exception("connector %s: listing tools failed", c.spec.name)
            c.error, c.loaded = str(exc) or exc.__class__.__name__, time.monotonic() - REFRESH_SECONDS + 60
            return
        allow = set(c.spec.tools) if c.spec.tools else None
        deny = set(c.spec.exclude)
        c.tools = {}
        for t in raw:
            name = t.get("name")
            if not name or (allow is not None and name not in allow) or name in deny:
                continue
            ct = ConnectorTool(
                connector=c.spec.name,
                name=name,
                title=t.get("title") or (t.get("annotations") or {}).get("title") or name,
                description=(t.get("description") or "").strip(),
                schema=t.get("inputSchema") or {"type": "object", "properties": {}},
                confirm=needs_confirmation(c.spec, t),
                read_only=read_only(t),
            )
            c.tools[ct.full_name] = ct
        c.error, c.loaded = None, time.monotonic()

    def reload(self) -> None:
        """Forget the tool lists: the next turn asks the servers again."""
        for c in self.items.values():
            c.loaded = 0.0

    async def tools_for(self, agent_id: str) -> dict[str, ConnectorTool]:
        out: dict[str, ConnectorTool] = {}
        for c in self.items.values():
            if not self._allows(c, agent_id):
                continue
            await self._load(c)
            out.update(self._agent_tools(c, agent_id))
        return out

    def instructions_for(self, agent_id: str) -> str:
        """What the servers of this agent's connectors say about their tools, for its prompt."""
        if not self.hq.settings.mcp_use_server_instructions:
            return ""
        parts = []
        for c in self.items.values():
            text = (getattr(c.client, "instructions", "") or "").strip()
            if text and self._allows(c, agent_id) and self._agent_tools(c, agent_id):
                parts.append(f"[{c.spec.name}] {text}")
        return "\n\nStrumenti dei connettori (MCP):\n" + "\n".join(parts) if parts else ""

    @staticmethod
    def definition(t: ConnectorTool) -> dict:
        desc = f"[{t.connector}] {t.description}".strip()
        if t.confirm:
            desc += " (Modifica i dati: viene mostrata al proprietario e parte solo dopo la sua conferma.)"
        return {"name": t.full_name, "description": desc[:1024], "input_schema": t.schema}

    def toolbox(self, extra: dict[str, ConnectorTool], defs: list[dict]) -> list[dict]:
        """The definitions to offer for `extra`. With mcp_tool_search on, only the always-loaded
        ones plus SEARCH_TOOL, which adds the others to `defs` (the turn's list) when found."""
        if not self.hq.settings.mcp_tool_search or len(extra) <= 12:
            return [self.definition(t) for t in extra.values()]
        shown = {k: t for k, t in extra.items() if t.name in ALWAYS_LOADED}
        hidden = {k: t for k, t in extra.items() if k not in shown}
        extra[SEARCH_TOOL] = SearchTool(defs, hidden, extra)  # type: ignore[assignment]
        return [self.definition(t) for t in shown.values()] + [{
            "name": SEARCH_TOOL,
            "description": (
                f"Cerca tra altri {len(hidden)} strumenti dei connettori (Home Assistant e programmi di "
                "lavoro) per parola chiave, es. 'luce', 'automazione', 'meteo', 'telecamera'. Gli "
                "strumenti trovati diventano subito utilizzabili."
            ),
            "input_schema": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Parole chiave"}}, "required": ["query"]},
        }]

    async def execute(self, t, args: dict, agent_id: str | None) -> tuple[str | list, bool]:
        if isinstance(t, SearchTool):
            return self._search(t, str(args.get("query") or "")), False
        if t.confirm:
            payload = {"connector": slug(t.connector), "tool": t.name, "args": args}
            return await self.hq.actions.propose("mcp", agent_id, summarize(t, args), payload, t.connector), False
        c = self.items[slug(t.connector)]
        s = self.hq.settings
        try:
            return await c.client.call_tool(t.name, args, images=s.mcp_image_results,
                                            max_chars=s.mcp_max_result_kb * 1000, agent_id=agent_id)
        except MCPError as exc:
            return f"{t.connector}: {exc}", True

    def _search(self, search: SearchTool, query: str) -> str:
        words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 1]
        scored = []
        for key, t in search.hidden.items():
            hay = f"{t.name} {t.title} {t.description}".lower()
            score = sum(hay.count(w) for w in words)
            if score:
                scored.append((score, key, t))
        scored.sort(key=lambda x: -x[0])
        found = scored[:8]
        known = {d["name"] for d in search.defs}
        for _, key, t in found:
            if key not in known:
                search.defs.append(self.definition(t))  # the next request of this turn offers it
            search.extra[key] = t
        if not found:
            return "Nessuno strumento trovato: prova altre parole."
        return "Ora puoi usare: " + ", ".join(f"{key} ({t.title})" for _, key, t in found)

    async def _run_confirmed(self, payload: dict) -> str:
        c = self.items.get(payload["connector"])
        if c is None:
            raise RuntimeError(tr("connettore non più configurato"))
        text, failed = await c.client.call_tool(payload["tool"], payload["args"], images=False)
        text = text if isinstance(text, str) else ""
        if failed:
            raise RuntimeError(text[:300])
        first = text.strip().splitlines()[0][:200] if text.strip() else ""
        return f"✅ fatto{': ' + first if first else ''}"

    async def status(self) -> list[str]:
        lines = []
        for c in self.items.values():
            c.loaded = 0.0  # /stato forces a fresh check
            await self._load(c)
            lines.append(f"{c.spec.name}: " + (f"⚠ {c.error}" if c.error else f"OK, {len(c.tools)} strumenti"))
        return lines

    def describe(self) -> list[dict[str, Any]]:
        return [{
            "name": c.spec.name, "tools": len(c.tools), "error": c.error, "builtin": c.builtin,
            "agents": c.spec.agents, "confirm": c.spec.confirm,
            "instructions": bool((getattr(c.client, "instructions", "") or "").strip()),
        } for c in self.items.values()]
