"""HubNEX as an MCP server: POST /mcp (Streamable HTTP, plain JSON answers, no server push).

Off unless the add-on page says mcp_expose. What it offers (mcp_expose_tools):
  ha        the Home Assistant tools of the built-in connector, under its rules (groups,
            protected entities, the owner's confirmation for changes not marked free);
  sessions  HubNEX's conversations: list them, read one, ask Jarvis in one;
  team      the team's status, and a task for an agent.
With mcp_expose_read_only (the default) only the tools that read are offered and answered.
"""

from __future__ import annotations

import hmac
import json
from typing import TYPE_CHECKING, Any

from hubnex import __version__
from hubnex.connectors import CASA

if TYPE_CHECKING:
    from hubnex.hq import HQ

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
CHANNEL = "mcp"  # the conversations an outside client starts

SESSION_TOOLS = [
    {"name": "list_sessions", "readOnly": True,
     "description": "HubNEX's conversations with Jarvis, most recent first: id, channel, title, when.",
     "inputSchema": {"type": "object", "properties": {
         "channel": {"type": "string", "description": "dashboard, mcp, assist, telegram:<chat>… Empty: all."},
         "limit": {"type": "integer", "minimum": 1, "maximum": 200}}}},
    {"name": "get_session", "readOnly": True,
     "description": "One conversation: what was said and the tools used on the way, oldest first.",
     "inputSchema": {"type": "object", "properties": {
         "session_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}},
         "required": ["session_id"]}},
    {"name": "ask_jarvis", "readOnly": False,
     "description": "Ask Jarvis (HubNEX's assistant, who can act on the house and delegate to the team). "
                    "Continues the conversation given, else the current one of the mcp channel.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"}, "session_id": {"type": "string"},
         "new_session": {"type": "boolean", "description": "Start a new conversation first."}},
         "required": ["text"]}},
]
TEAM_TOOLS = [
    {"name": "team_status", "readOnly": True,
     "description": "Jarvis and the agents: what each one is doing now and its last result.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "give_task", "readOnly": False,
     "description": "Give an agent of the team a task; answers with the agent's report.",
     "inputSchema": {"type": "object", "properties": {
         "agent_id": {"type": "string"}, "task": {"type": "string"}}, "required": ["agent_id", "task"]}},
]


def authorized(hq: "HQ", header: str | None) -> bool:
    token = hq.settings.mcp_token or hq.settings.hq_token
    if not token or not header or not header.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(header[7:].strip().encode(), token.encode())


class Exposed:
    def __init__(self, hq: "HQ"):
        self.hq = hq

    # ------------------------------------------------------------------ the catalogue
    async def _casa(self) -> dict:
        c = self.hq.connectors.items.get(CASA)
        if c is None:
            return {}
        await self.hq.connectors._load(c)
        return {t.name: t for t in c.tools.values()}

    async def tools(self) -> list[dict]:
        s = self.hq.settings
        ro = s.mcp_expose_read_only
        out: list[dict] = []
        if "ha" in s.mcp_expose_tools:
            for t in (await self._casa()).values():
                if ro and not t.read_only:
                    continue
                out.append({"name": t.name, "description": t.description, "inputSchema": t.schema,
                            "annotations": {"readOnlyHint": t.read_only}})
        for group, specs in (("sessions", SESSION_TOOLS), ("team", TEAM_TOOLS)):
            if group not in s.mcp_expose_tools:
                continue
            for t in specs:
                if ro and not t["readOnly"]:
                    continue
                out.append({"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"],
                            "annotations": {"readOnlyHint": t["readOnly"]}})
        return out

    # ------------------------------------------------------------------ JSON-RPC
    async def handle(self, msg: Any) -> dict | list | None:
        if isinstance(msg, list):
            answers = [a for a in [await self.handle(m) for m in msg] if a is not None]
            return answers or None
        if not isinstance(msg, dict):
            return _error(None, -32600, "invalid request")
        mid, method, params = msg.get("id"), msg.get("method", ""), msg.get("params") or {}
        if mid is None:  # a notification (initialized, cancelled…): nothing to answer
            return None
        try:
            if method == "initialize":
                asked = params.get("protocolVersion")
                return _result(mid, {
                    "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "hubnex", "version": __version__},
                    "instructions": self.instructions(),
                })
            if method == "ping":
                return _result(mid, {})
            if method == "tools/list":
                return _result(mid, {"tools": await self.tools()})
            if method == "tools/call":
                return _result(mid, await self.call(str(params.get("name", "")), params.get("arguments") or {}))
            if method in ("resources/list", "prompts/list"):
                return _result(mid, {method.split("/")[0]: []})
            return _error(mid, -32601, f"method not found: {method}")
        except Exception as exc:  # noqa: BLE001 — answered, never a 500
            return _error(mid, -32603, str(exc) or exc.__class__.__name__)

    def instructions(self) -> str:
        from hubnex.mcp_server.catalog import INSTRUCTIONS

        s = self.hq.settings
        parts = ["HubNEX: an AI headquarters for home and work, with Jarvis and a team of agents."]
        if "ha" in s.mcp_expose_tools:
            parts.append(INSTRUCTIONS.replace("casa__…", "these"))
        if "sessions" in s.mcp_expose_tools:
            parts.append("Conversations: list_sessions, get_session; ask_jarvis to ask the assistant.")
        if "team" in s.mcp_expose_tools:
            parts.append("Team: team_status; give_task to give an agent a task.")
        if s.mcp_expose_read_only:
            parts.append("This connection is read-only.")
        return " ".join(parts)

    async def call(self, name: str, args: dict) -> dict:
        allowed = {t["name"]: t for t in await self.tools()}
        if name not in allowed:
            return _text(f"Unknown or not offered tool: {name}", True)
        casa = await self._casa() if "ha" in self.hq.settings.mcp_expose_tools else {}
        if name in casa:
            out, failed = await self.hq.connectors.execute(casa[name], args, "mcp")
            return _content(out, failed)
        hq = self.hq
        if name == "list_sessions":
            rows = await hq.store.sessions(args.get("channel") or None, limit=int(args.get("limit") or 50))
            return _text(json.dumps([{k: r[k] for k in ("id", "channel", "title", "updated", "messages")}
                                     for r in rows], ensure_ascii=False))
        if name == "get_session":
            sess = await hq.store.session_get(str(args["session_id"]))
            if not sess or sess["deleted_at"] is not None:
                return _text("conversation not found", True)
            rows = await hq.store.session_transcript(sess["id"], limit=int(args.get("limit") or 200))
            return _text(json.dumps({"title": sess["title"], "channel": sess["channel"], "events": [
                {"role": r["role"], "kind": r["kind"], "text": r["text"]} for r in rows]}, ensure_ascii=False))
        if name == "ask_jarvis":
            sid = args.get("session_id")
            if args.get("new_session"):
                sid = await hq.new_session(CHANNEL)
            try:
                sid = await hq.session_for(CHANNEL, sid)
            except KeyError:
                return _text("conversation not found", True)
            reply, _, by = await hq.converse(CHANNEL, str(args["text"]), session_id=sid)
            return _text(json.dumps({"reply": reply, "by": by, "session_id": sid}, ensure_ascii=False))
        if name == "team_status":
            return _text(json.dumps([{"id": a.id, "name": a.name, "role": a.role, "status": a.status,
                                      "task": a.task, "last_result": (a.last_result or "")[:1000]}
                                     for a in hq.agents.values()], ensure_ascii=False))
        if name == "give_task":
            if hq.org.agent(str(args["agent_id"])) is None:
                return _text("unknown agent", True)
            return _text(await hq.run_agent(str(args["agent_id"]), str(args["task"]), "user"))
        return _text(f"Unknown tool: {name}", True)


def _content(out, failed: bool) -> dict:
    """A tool's answer (text, or Anthropic content blocks) as MCP content."""
    if isinstance(out, str):
        return _text(out, failed)
    content = []
    for b in out:
        if b.get("type") == "image":
            src = b.get("source") or {}
            content.append({"type": "image", "data": src.get("data", ""), "mimeType": src.get("media_type", "image/jpeg")})
        elif b.get("type") == "text":
            content.append({"type": "text", "text": b.get("text", "")})
    return {"content": content, **({"isError": True} if failed else {})}


def _text(text: str, error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], **({"isError": True} if error else {})}


def _result(mid, result) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}
