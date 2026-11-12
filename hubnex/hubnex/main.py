"""FastAPI app: dashboard, REST API, live WebSocket, background workers."""

from __future__ import annotations

import asyncio
import os
import json
import base64
import hmac
import secrets
import time
import mimetypes
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hubnex import __version__
from hubnex.addon import setup_assist
from hubnex.attachments import MAX_BYTES, MAX_PER_MESSAGE, AttachmentError
from hubnex.backup import BackupError, apply_pending_restore, make_backup, stage_restore
from hubnex.casa import SUGGEST_SCHEMA, LayoutError, clean_suggestion, downsample, suggest_prompt
from hubnex.energy import band_until, day_profile
from hubnex.llm import complete
from hubnex.integrations.ha_ws import HAWatcherError
from hubnex.integrations.homeassistant import HomeAssistantError
from hubnex.config import Settings, load_org
from hubnex.context import ORIGIN
from hubnex.graph import build_graph
from hubnex.speech import for_voice
from hubnex.i18n import REQUEST_LANG, norm, tr, tr_sys
from hubnex.hq import HQ
from hubnex.actions import ActionClosed
from hubnex.maildesk import DraftClosed
from hubnex.scheduler import Scheduler
from hubnex.store import Store

log = logging.getLogger("hubnex")
mimetypes.add_type("application/manifest+json", ".webmanifest")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


# Request bodies live at module level: FastAPI must resolve these annotations by name.
class ChatIn(BaseModel):
    text: str = Field(default="", max_length=8000)
    attachments: list[str] = Field(default=[], max_length=MAX_PER_MESSAGE)  # ids from /api/attachments
    channel: str = "dashboard"
    voice: bool = False  # the answer will be spoken (Assist): keep it short
    speak: bool = False  # the dashboard will read the answer aloud too
    # The dashboard doesn't wait on one long request (a proxy may cut it after a minute or
    # two): it gets a job id at once and asks for the answer with short requests.
    background: bool = False


class TaskIn(BaseModel):
    task: str = Field(min_length=1, max_length=8000)
    attachments: list[str] = Field(default=[], max_length=MAX_PER_MESSAGE)
    wait: bool = False


class DeadlineIn(BaseModel):
    title: str
    due: str
    notes: str = ""
    company: str | None = None


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=2500)


class ReviseIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class HAEventIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    notify: bool = True


class ServiceIn(BaseModel):
    domain: str = Field(pattern=r"^[a-z_]+$")
    service: str = Field(pattern=r"^[a-z_]+$")
    data: dict = Field(default_factory=dict)


class RoomEntityIn(BaseModel):
    entity_id: str = Field(pattern=r"^[a-z_]+\.[A-Za-z0-9_]+$")
    mode: Literal["ha", "local"] = "ha"  # move the area in Home Assistant, or only show it here


class RoomTempIn(BaseModel):
    entity_id: str | None = None  # None: back to the automatic choice


class KindIn(BaseModel):
    kind: Literal["light", "switch", "gate", "siren", "sensor", "stock"] | None = None  # None: as in Home Assistant


class StockIn(BaseModel):
    delivery: int = Field(ge=1, le=1000)  # how many come in a delivery
    low: int = Field(ge=0, le=1000)  # warn below this


BLOCK_KINDS = Literal["value", "ring", "toggle", "button", "slider", "chart", "bar", "band", "select", "state", "text", "camera", "media", "ask"]
CARD_COLOR = Literal["", "warm", "cool", "green", "violet", "red"]
COMPARE = Literal["<", ">", "=", "!="]


class RuleIn(BaseModel):
    """A colour by value: when the block's entity is below / above / equal to `v`."""
    op: COMPARE
    v: str = Field(max_length=60)
    c: CARD_COLOR


class ShowIn(BaseModel):
    """The block is shown only when this entity compares so."""
    e: str = Field(max_length=255)
    op: COMPARE = "="
    v: str = Field(default="on", max_length=60)


class TapIn(BaseModel):
    """What a tap on the block does."""
    do: Literal["toggle", "run", "ask", "room"]
    e: str = Field(default="", max_length=255)  # toggle / run: which entity (empty: the block's)
    text: str = Field(default="", max_length=300)  # ask: the question for Jarvis
    area: str = Field(default="", max_length=100)  # room: which one


class BlockIn(BaseModel):
    """A block of a free card: what it shows, of which entity, how big on the 4-column grid."""
    kind: BLOCK_KINDS
    entity: str = Field(default="", max_length=255)
    entity2: str = Field(default="", max_length=255)  # the band's end time
    label: str = Field(default="", max_length=60)
    w: int = Field(default=1, ge=1, le=4)
    h: int = Field(default=1, ge=1, le=2)
    min: float | None = None  # ring and bar: their scale
    max: float | None = None
    rules: list[RuleIn] = Field(default_factory=list, max_length=4)
    show: ShowIn | None = None
    tap: TapIn | None = None


class DraftIn(BaseModel):
    text: str = Field(min_length=3, max_length=1000)


class CardIn(BaseModel):
    id: str | None = Field(default=None, pattern=r"^c[0-9]{1,4}$")
    name: str = Field(max_length=60)
    entities: list[str] = Field(default_factory=list, max_length=24)
    kind: Literal["composed", "free"] = "composed"
    blocks: list[BlockIn] = Field(default_factory=list, max_length=24)
    color: CARD_COLOR = ""
    style: Literal["", "flat"] = ""  # free card: blocks in boxes, or flat (no boxes)
    size: Literal["small", "wide"] = "wide"
    group: str | None = Field(default=None, pattern=r"^[a-z]{1,20}$")  # the room's group it sits in (None: of its first entity)
    enable: str | None = Field(default=None, max_length=255)  # the switch that turns the card's times on ("automatica"); "" = none
    nochart: list[str] = Field(default_factory=list, max_length=12)  # sensors shown without their chart


class OrderIn(BaseModel):
    items: list[str] = Field(max_length=300)


class DisplayIn(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    size: Literal["small", "wide"] | None = None
    chart: bool | None = None  # the sensor's 24-hour chart on its card


class LayoutIn(BaseModel):
    text: str = Field(max_length=200_000)


class PlanRoomIn(BaseModel):
    area: str = Field(min_length=1, max_length=80)
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    points: list[dict[str, float]] | None = Field(default=None, max_length=32)
    outline: bool = False


class PlanFloorIn(BaseModel):
    name: str = Field(default="Piano", max_length=60)
    aspect: float = 1.4
    image: str | None = None
    rooms: list[PlanRoomIn] = Field(default_factory=list, max_length=80)


class PlanIn(BaseModel):
    floors: list[PlanFloorIn] = Field(max_length=10)
    outside: list[str] = Field(default_factory=list)
    energy: dict[str, str] = Field(default_factory=dict)


class SuggestIn(BaseModel):
    image: str


# What a Home Assistant user who is not an administrator may do from the house view: the
# devices' own services, as in Home Assistant itself (never e.g. hassio.* or recorder.*).
HOUSE_DOMAINS = {
    "light", "switch", "fan", "cover", "climate", "lock", "alarm_control_panel", "media_player",
    "scene", "script", "button", "input_button", "input_boolean", "input_select", "input_number",
    "select", "number", "vacuum", "valve", "siren", "humidifier", "water_heater", "lawn_mower",
    "input_datetime", "time", "date", "datetime", "input_text", "text", "counter",
}
HOUSE_EVENTS = {"ha", "casa_changed"}


def clean_card(hq, data: dict, keep_missing: bool) -> dict:
    """A card from outside (Claude's draft, an import) made safe for the editor: valid blocks only,
    entities that exist; `keep_missing`: a missing one leaves its block empty instead of dropping it."""
    known = hq.watcher.states
    blocks, dropped, missing = [], 0, 0
    for b in (data.get("blocks") or [])[:24]:
        try:
            blk = BlockIn(**b) if isinstance(b, dict) else None
        except ValueError:
            blk = None
        if blk is None:
            dropped += 1
            continue
        if blk.show and blk.show.e not in known:
            blk.show = None
        if blk.tap and blk.tap.e and blk.tap.e not in known:
            blk.tap.e = ""
        gone = [f for f in ("entity", "entity2") if getattr(blk, f) and getattr(blk, f) not in known]
        need = blk.kind not in ("text", "ask") and (not blk.entity or blk.entity in gone or blk.kind == "band" and (not blk.entity2 or "entity2" in gone))
        if gone or need:
            if not keep_missing:
                dropped += 1  # an entity that doesn't exist (made up, or of another house)
                continue
            for f in gone:
                setattr(blk, f, "")
            missing += 1
        blocks.append({k: v for k, v in blk.model_dump(exclude_none=True).items() if v != []})
    used = {e for b in blocks for e in (b.get("entity"), b.get("entity2"), (b.get("show") or {}).get("e"), (b.get("tap") or {}).get("e")) if e}
    color = data.get("color") if data.get("color") in ("", "warm", "cool", "green", "violet", "red") else ""
    return {
        "name": str(data.get("name") or "")[:60], "color": color, "style": data.get("style") if data.get("style") in ("", "flat") else None, "blocks": blocks, "dropped": dropped, "missing": missing,
        "states": {e: hq.casa.compact(e) for e in used},  # so the editor shows them at once
    }


def stock_stats(points: list[tuple[str, str]], now: datetime) -> dict:
    """From a stock's history: how many go per day (what went down, over the days seen), the
    days left at that pace, and when the last delivery came (the last rise)."""
    vals = []
    for t, v in points:
        try:
            vals.append((datetime.fromisoformat(t.replace("Z", "+00:00")), float(v)))
        except (TypeError, ValueError):
            continue  # unavailable, unknown
    if len(vals) < 2:
        return {"per_day": None, "days_left": None, "last_delivery": None}
    used = sum(max(0.0, a[1] - b[1]) for a, b in zip(vals, vals[1:]))
    rises = [b[0] for a, b in zip(vals, vals[1:]) if b[1] > a[1]]
    days = max(1.0, (now - vals[0][0]).total_seconds() / 86400)
    per_day = used / days if used else None
    left = vals[-1][1]
    return {
        "per_day": round(per_day, 2) if per_day else None,
        "days_left": int(left / per_day) if per_day else None,
        "last_delivery": rises[-1].isoformat() if rises else None,
    }


def house_service(domain: str, service: str) -> bool:
    if domain == "homeassistant":
        return service in ("turn_on", "turn_off", "toggle")
    return domain in HOUSE_DOMAINS


def house_only(state: dict) -> dict:
    """The snapshot for whoever only gets the house: no team, activity, mail or spending."""
    return {
        "role": "casa",
        "boss": state["boss"],
        "version": state["version"],
        "companies": [], "agents": [], "routines": {}, "logs": [], "deadlines": [], "drafts": [], "actions": [],
        "stats": {k: 0 for k in state["stats"]},
        "integrations": {"home_assistant": state["integrations"]["home_assistant"], "telegram": False,
                         "voice": False, "mail": False, "connectors": []},
    }


def config_dir(settings: Settings) -> Path:
    """The folder with agents.yaml, casa.yaml and the floor plan images."""
    return Path(settings.casa_file).parent if settings.casa_file else Path(settings.agents_file).parent


async def restart_addon() -> bool:
    """Ask the Supervisor to restart this add-on (after a restore). False outside an add-on."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return False
    await asyncio.sleep(1.5)  # let the answer reach the browser first
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("http://supervisor/addons/self/restart", headers={"Authorization": f"Bearer {token}"})
    return r.status_code < 400


def create_app(settings: Settings | None = None, hq: HQ | None = None, start_workers: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal hq
        restored = None
        if hq is None:
            # A backup restored from the dashboard: put in place before the database is opened.
            restored = apply_pending_restore(settings.db_path, config_dir(settings))
            hq = HQ(settings, load_org(settings.agents_file), Store(settings.db_path))
        await hq.load()
        if restored:
            await hq.log("system", tr_sys("Backup ripristinato (HubNEX {version} del {date}).", version=restored.get('version', '?'), date=restored.get('created', '?')))
        app.state.hq = hq
        if start_workers and settings.trusted_proxy:  # running as a Home Assistant add-on
            await setup_assist(hq)
        workers: list[asyncio.Task] = []
        if start_workers:
            workers.append(asyncio.create_task(Scheduler(hq).run()))
            if hq.team_enabled:
                await hq.team.start()
            if hq.maildesk:
                workers.append(asyncio.create_task(hq.maildesk.loop()))
            if hq.watcher.enabled:
                workers.append(asyncio.create_task(hq.watcher.run()))
                workers.append(asyncio.create_task(hq.alerts.run()))
            if not settings.hq_token and not settings.trusted_proxy:
                log.warning("HQ_TOKEN non impostato: dashboard e API sono aperte a chiunque in rete!")
        await hq.log("system", tr_sys("{name} è online. {n} agenti nel team.", name=hq.org.boss_name, n=len(hq.org.agents)))
        yield
        for w in workers:
            w.cancel()
        if start_workers and hq.team_enabled:
            await hq.team.stop()
        login = claude_login["process"]
        if login and login.returncode is None:
            login.terminate()
            await login.wait()
        await hq.close()

    app = FastAPI(title="HubNEX", lifespan=lifespan)

    def check_token(token: str | None, client_host: str | None) -> None:
        if settings.trusted_proxy and client_host == settings.trusted_proxy:
            return  # opened from the HA sidebar (ingress): HA already checked who you are
        for valid in (settings.hq_token, settings.internal_token):
            if valid and token and hmac.compare_digest(token, valid):
                return
        if not settings.hq_token and not settings.trusted_proxy:
            return  # standalone without a token: open (warned at startup)
        # As an add-on with no token set, only the HA sidebar may get in.
        raise HTTPException(401, tr("token mancante o errato"))

    async def role_of(client_host: str | None, headers) -> str:
        """"full", or "casa" for a Home Assistant user who is not an administrator: the sidebar
        panel is open to every user, so the add-on checks who is asking (Supervisor headers)."""
        if not (settings.trusted_proxy and client_host == settings.trusted_proxy) or settings.non_admin_access == "completo":
            return "full"  # the token was checked already
        user = headers.get("x-remote-user-id")
        watcher = app.state.hq.watcher
        try:
            if watcher.enabled and not watcher.ready.is_set():
                await asyncio.wait_for(watcher.ready.wait(), 10)  # just started
            if user and await watcher.is_admin(user):
                return "full"
        except Exception as exc:
            log.warning("Non so se l'utente %s è amministratore (%s): solo Casa", user, exc)
        return "casa"

    async def auth(request: Request) -> str:
        header = request.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token")
        host = request.client.host if request.client else None
        check_token(token, host)
        return await role_of(host, request.headers)

    async def full(role: str = Depends(auth)) -> None:
        if role != "full":
            raise HTTPException(403, tr("riservato agli amministratori di Home Assistant"))

    def get_hq(request: Request) -> HQ:
        return request.app.state.hq

    # ------------------------------------------------------------- dashboard
    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.middleware("http")
    async def revalidate_dashboard(request: Request, call_next):
        # Browsers (and the HA app) must check for a newer dashboard after an update instead
        # of showing the cached one: "no-cache" still allows a cheap 304 when nothing changed.
        # The viewer's language (the dashboard sends it): errors and answers to this request.
        token = REQUEST_LANG.set(norm(request.headers.get("x-hubnex-lang")))
        try:
            response = await call_next(request)
        finally:
            REQUEST_LANG.reset(token)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    # ------------------------------------------------------------- API
    @app.get("/api/ping", dependencies=[Depends(auth)])
    async def ping(hq: HQ = Depends(get_hq)):
        return {"name": hq.org.boss_name}

    @app.get("/api/claude/auth", dependencies=[Depends(full)])
    async def claude_auth(hq: HQ = Depends(get_hq)):
        from hubnex.claude_code import auth_status

        status = await auth_status() if settings.claude_auth_mode != "api_key" else {"status": "off", "detail": ""}
        return {"mode": settings.claude_auth_mode, "subscription_enabled": settings.claude_subscription_enabled,
                "api_key_available": bool(os.environ.get("ANTHROPIC_API_KEY")),
                "api_fallback": settings.claude_auth_mode == "hybrid" and settings.claude_api_fallback,
                "subscription": status, "last_error": hq.client.claude_error}

    claude_login: dict = {"process": None, "output": "", "task": None}

    async def read_claude_login(master: int, process):
        try:
            while True:
                try:
                    chunk = await asyncio.to_thread(os.read, master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                # The CLI owns authentication; keep only its terminal instructions in memory.
                import re
                clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", chunk.decode(errors="replace"))
                claude_login["output"] = (claude_login["output"] + clean)[-6000:]
            await process.wait()
        finally:
            os.close(master)

    @app.post("/api/claude/login", dependencies=[Depends(full)])
    async def claude_login_start():
        if settings.claude_auth_mode == "api_key" or not settings.claude_subscription_enabled:
            raise HTTPException(400, "Abbonamento Claude non attivato")
        if claude_login["process"] and claude_login["process"].returncode is None:
            return {"running": True, "output": claude_login["output"]}
        from hubnex.claude_code import cli_env
        import pty
        import shutil
        import termios

        binary = shutil.which("claude")
        if not binary:
            raise HTTPException(503, "Claude Code non installato")
        master, slave = pty.openpty()
        attrs = termios.tcgetattr(slave)
        attrs[3] &= ~termios.ECHO  # never echo a pasted login code into the dashboard
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        try:
            process = await asyncio.create_subprocess_exec(binary, "auth", "login", stdin=slave,
                                                            stdout=slave, stderr=slave, env=cli_env())
        except OSError:
            os.close(master)
            raise HTTPException(503, "Impossibile avviare Claude Code")
        finally:
            os.close(slave)
        claude_login.update(process=process, master=master, output="", task=asyncio.create_task(
            read_claude_login(master, process)))
        return {"running": True, "output": ""}

    @app.get("/api/claude/login", dependencies=[Depends(full)])
    async def claude_login_progress():
        process = claude_login["process"]
        return {"running": bool(process and process.returncode is None), "output": claude_login["output"]}

    @app.post("/api/claude/login/code", dependencies=[Depends(full)])
    async def claude_login_code(body: dict):
        process = claude_login["process"]
        code = body.get("code")
        if not process or process.returncode is not None or not isinstance(code, str) or not 1 <= len(code) <= 512:
            raise HTTPException(400, "Nessun accesso Claude in attesa di un codice")
        os.write(claude_login["master"], (code.strip() + "\n").encode())
        return {"running": True}

    @app.get("/api/logs", dependencies=[Depends(full)])
    async def logs(before: int | None = None, limit: int = 25, hq: HQ = Depends(get_hq)):
        """Older activity for the dashboard's "Mostra precedenti" button."""
        return await hq.store.recent_logs(min(limit, 100), before_id=before)

    @app.get("/api/alerts", dependencies=[Depends(full)])
    async def alerts_get(hq: HQ = Depends(get_hq)):
        """Smart notifications: settings, phones, watched entities, what is active now."""
        return await hq.alerts.overview()

    @app.put("/api/alerts", dependencies=[Depends(full)])
    async def alerts_put(body: dict, hq: HQ = Depends(get_hq)):
        await hq.alerts.save(body)
        return await hq.alerts.overview()

    @app.post("/api/alerts/test", dependencies=[Depends(full)])
    async def alerts_test(hq: HQ = Depends(get_hq)):
        return {"sent": await hq.alerts.test()}

    @app.get("/api/costs", dependencies=[Depends(full)])
    async def costs(days: int = 30, hq: HQ = Depends(get_hq)):
        """Claude spend history: per day, per agent, per model, this month and the budget."""
        return await hq.costs(days)

    @app.get("/api/graph", dependencies=[Depends(full)])
    async def graph(hq: HQ = Depends(get_hq)):
        return await build_graph(hq)

    @app.get("/api/state", dependencies=[Depends(full)])
    async def state(hq: HQ = Depends(get_hq)):
        return await hq.snapshot()

    chat_jobs: dict[str, dict] = {}  # job id -> {"at": time, "done": bool, "out": answer, "error": text}

    @app.post("/api/chat", dependencies=[Depends(full)])
    async def chat(body: ChatIn, hq: HQ = Depends(get_hq)):
        # Dashboard: Home Assistant's own sentences first, then the quick route, then Jarvis.
        # Assist: Home Assistant already tried its sentences, so the quick route, then Jarvis.
        dashboard = body.channel == "dashboard"
        files = attachments_for(hq, body.attachments)
        if not body.text.strip() and not files:
            raise HTTPException(422, tr("scrivi un messaggio o allega un file"))

        async def answer() -> dict:
            reply, spoken, by = await hq.converse(
                body.channel, body.text, voice=body.voice, spoken=body.speak,
                quick=body.voice or dashboard, local=dashboard, attachments=files,
            )
            if body.voice and reply:
                reply = for_voice(reply)  # Assist reads it aloud: units and symbols as words
            out = {"reply": reply or tr("L'agente ha risposto direttamente nel gruppo Telegram."), "by": by}
            if spoken:
                out["spoken"] = spoken  # what the voice says of a long answer ("riassunto")
            return out

        if not body.background:
            return await answer()
        now = time.time()
        for k in [k for k, j in chat_jobs.items() if now - j["at"] > 3600]:
            del chat_jobs[k]  # answers nobody came back for
        job_id = secrets.token_urlsafe(9)
        job = chat_jobs[job_id] = {"at": now, "done": False}

        async def run() -> None:
            try:
                job["out"] = await answer()
            except Exception as exc:
                log.exception("chat failed")
                job["error"] = str(exc) or exc.__class__.__name__
            job["done"] = True

        job["task"] = asyncio.create_task(run())
        return {"job": job_id}

    @app.get("/api/chat/{job_id}", dependencies=[Depends(full)])
    async def chat_job(job_id: str):
        job = chat_jobs.get(job_id)
        if job is None:
            raise HTTPException(404, tr("risposta non trovata"))
        if not job["done"]:
            return {"done": False}
        chat_jobs.pop(job_id, None)
        if "error" in job:
            raise HTTPException(502, job["error"])
        return {"done": True, **job["out"]}

    @app.get("/api/agents/{agent_id}", dependencies=[Depends(full)])
    async def agent_detail(agent_id: str, hq: HQ = Depends(get_hq)):
        if agent_id not in hq.agents:
            raise HTTPException(404, tr("agente sconosciuto"))
        return {"tasks": await hq.store.agent_tasks(agent_id, 10)}

    @app.post("/api/agents/{agent_id}/task", dependencies=[Depends(full)])
    async def assign(agent_id: str, body: TaskIn, hq: HQ = Depends(get_hq)):
        if hq.org.agent(agent_id) is None:
            raise HTTPException(404, tr("agente sconosciuto"))
        files = attachments_for(hq, body.attachments)
        if body.wait:
            return {"result": await hq.run_agent(agent_id, body.task, source="user", attachments=files)}
        hq.run_agent_background(agent_id, body.task, source="user", report=False, attachments=files)
        return {"status": "started"}

    # ------------------------------------------------------------------ attachments
    def attachments_for(hq: HQ, ids: list[str]):
        files, missing = hq.attachments.find(ids)
        if missing:
            raise HTTPException(404, tr("allegato non trovato: {ids}", ids=", ".join(missing)))
        return files

    @app.post("/api/attachments", dependencies=[Depends(full)])
    async def attachment_upload(request: Request, name: str = "", hq: HQ = Depends(get_hq)):
        """A photo, PDF or text file (raw body) for the next message: its id goes in `attachments`."""
        if int(request.headers.get("content-length") or 0) > MAX_BYTES:
            raise HTTPException(413, tr("file troppo grande (massimo 20 MB)"))
        data = await request.body()
        try:
            att = await asyncio.to_thread(hq.attachments.save, data, name, request.headers.get("content-type"))
        except AttachmentError as exc:
            raise HTTPException(422, str(exc))
        return {"id": att.id, "name": att.name, "kind": att.kind, "pages": att.pages}

    @app.get("/api/attachments/{att_id}", dependencies=[Depends(full)])
    async def attachment_get(att_id: str, hq: HQ = Depends(get_hq)):
        att = hq.attachments.get(att_id)
        if att is None:
            raise HTTPException(404, tr("allegato non trovato: {ids}", ids=att_id))
        return FileResponse(
            hq.attachments.path(att), media_type=hq.attachments.media_type(att),
            headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
        )

    @app.post("/api/deadlines", dependencies=[Depends(full)])
    async def add_deadline(body: DeadlineIn, hq: HQ = Depends(get_hq)):
        try:
            datetime.fromisoformat(body.due)
        except ValueError:
            raise HTTPException(422, tr("data non valida, usa AAAA-MM-GG"))
        did = await hq.store.deadline_add(body.title, body.due, body.company, None, body.notes)
        await hq.emit_deadlines()
        return {"id": did}

    @app.post("/api/deadlines/{deadline_id}/done", dependencies=[Depends(full)])
    async def done_deadline(deadline_id: int, hq: HQ = Depends(get_hq)):
        await hq.store.deadline_done(deadline_id)
        await hq.emit_deadlines()
        return {"ok": True}

    def desk(hq: HQ):
        if hq.maildesk is None:
            raise HTTPException(503, tr("casella email non configurata"))
        return hq.maildesk

    @app.post("/api/drafts/{draft_id}/revise", dependencies=[Depends(full)])
    async def revise_draft(draft_id: int, body: ReviseIn, hq: HQ = Depends(get_hq)):
        d = await hq.store.draft(draft_id)
        if not d:
            raise HTTPException(404, tr("bozza sconosciuta"))
        try:
            await desk(hq).revise(d, body.text)
        except DraftClosed:
            raise HTTPException(409, tr("Bozza non più attiva"))
        return {"ok": True}

    @app.post("/api/drafts/{draft_id}/{action}", dependencies=[Depends(full)])
    async def finish_draft(draft_id: int, action: Literal["send", "save", "drop"], hq: HQ = Depends(get_hq)):
        try:
            note = await desk(hq).finish(draft_id, action)
        except DraftClosed:
            raise HTTPException(409, tr("Bozza non più attiva"))
        return {"ok": True, "note": note}

    @app.post("/api/actions/{action_id}/{decision}", dependencies=[Depends(full)])
    async def decide_action(action_id: int, decision: Literal["ok", "no"], hq: HQ = Depends(get_hq)):
        try:
            note = await hq.actions.decide(action_id, decision == "ok")
        except ActionClosed:
            raise HTTPException(409, tr("Azione non più in attesa"))
        except Exception as exc:
            raise HTTPException(502, str(exc))
        return {"ok": True, "note": note}

    @app.post("/api/tts", dependencies=[Depends(full)])
    async def tts(body: TTSIn, hq: HQ = Depends(get_hq)):
        if not hq.tts_enabled:
            raise HTTPException(503, tr("Voce non configurata (ElevenLabs o sintesi vocale di Home Assistant)"))
        try:
            audio, ctype = await hq.speak_audio(body.text)
        except Exception as exc:
            raise HTTPException(502, str(exc))
        return Response(audio, media_type=ctype)

    @app.post("/api/ha/event", dependencies=[Depends(full)])
    async def ha_event(body: HAEventIn, hq: HQ = Depends(get_hq)):
        """Home Assistant automations push events here (rest_command) for Jarvis to handle."""
        ORIGIN.set("event")  # an automation, not the owner: Jarvis can only look and report
        reply = await hq.chat("homeassistant", f"[Evento da Home Assistant] {body.message}")
        if body.notify and reply:
            await hq.notify(f"🏠 {reply}")
        return {"reply": reply}

    # ------------------------------------------------------------- house view
    def need_ha(hq: HQ) -> None:
        if not hq.watcher.enabled:
            raise HTTPException(503, tr("Home Assistant non configurato"))

    forecast_cache: dict = {}

    @app.get("/api/casa/forecast", dependencies=[Depends(auth)])
    async def casa_forecast(hq: HQ = Depends(get_hq)):
        """The weather forecast for the house view, asked to Home Assistant at most every 30 min."""
        need_ha(hq)
        eid = hq.casa.build().get("weather")
        if not eid:
            return {"forecast": []}
        hit = forecast_cache.get(eid)
        if hit and time.time() - hit[0] < 1800:
            return {"forecast": hit[1]}
        try:
            days = await hq.ha.forecast(eid)
        except Exception as exc:  # an old Home Assistant or a weather service without forecast
            log.info("forecast unavailable: %s", exc)
            days = []
        forecast_cache[eid] = (time.time(), days)
        return {"forecast": days}

    @app.get("/api/casa", dependencies=[Depends(auth)])
    async def casa(hq: HQ = Depends(get_hq)):
        need_ha(hq)
        return hq.casa.build()

    @app.post("/api/casa/call", dependencies=[Depends(auth)])
    async def casa_call(body: ServiceIn, hq: HQ = Depends(get_hq), role: str = Depends(auth)):
        """A button pressed by the owner in the house view: no AI involved."""
        need_ha(hq)
        if role != "full" and not house_service(body.domain, body.service):
            raise HTTPException(403, f"{body.domain}.{body.service}: {tr('riservato agli amministratori di Home Assistant')}")
        try:
            await hq.ha.call_service(body.domain, body.service, body.data, by_owner=True)
        except HomeAssistantError as exc:
            raise HTTPException(502, str(exc))
        target = body.data.get("entity_id", "")
        await hq.log("ha", f"{tr_sys('Tu (Casa)')}: {body.domain}.{body.service} {target if isinstance(target, str) else ', '.join(target)}", None)
        return {"ok": True}

    @app.get("/api/casa/camera/{entity_id}", dependencies=[Depends(auth)])
    async def casa_camera(entity_id: str, hq: HQ = Depends(get_hq)):
        """A frame of the camera, fetched by the add-on (works from the sidebar and outside)."""
        need_ha(hq)
        if not entity_id.startswith(("camera.", "image.")):  # image.*: e.g. a robot vacuum's map
            raise HTTPException(404, tr("non è una telecamera"))
        try:
            image, ctype = await hq.ha.camera_image(entity_id)
        except HomeAssistantError as exc:
            raise HTTPException(502, str(exc))
        # Each refresh asks for a new URL (?t=…): a short cache avoids flicker on redraws.
        return Response(image, media_type=ctype, headers={"Cache-Control": "private, max-age=30"})

    @app.get("/api/casa/camera/{entity_id}/stream", dependencies=[Depends(auth)])
    async def casa_camera_stream(entity_id: str, hq: HQ = Depends(get_hq)):
        """Live MJPEG through the add-on: used when the HA video player (HLS) isn't reachable."""
        need_ha(hq)
        if not entity_id.startswith("camera."):
            raise HTTPException(404, tr("non è una telecamera"))
        try:
            ctype, chunks = await hq.ha.camera_stream(entity_id)
        except HomeAssistantError as exc:
            raise HTTPException(502, str(exc))
        return StreamingResponse(chunks, media_type=ctype, headers={"Cache-Control": "no-store"})

    @app.get("/api/casa/history", dependencies=[Depends(auth)])
    async def casa_history(e: str, hours: int = 24, hq: HQ = Depends(get_hq)):
        """The last day of the sensors on a room page, for their little charts."""
        need_ha(hq)
        eids = [x for x in e.split(",") if x in hq.casa.shown][:20]  # only what the house shows
        if not eids:
            return {}
        try:
            raw = await hq.ha.history(eids, max(1, min(hours, 72)))
        except HomeAssistantError as exc:
            raise HTTPException(502, str(exc))
        return {eid: downsample(points) for eid, points in raw.items()}

    @app.get("/api/casa/stock/{entity_id}", dependencies=[Depends(auth)])
    async def casa_stock(entity_id: str, hq: HQ = Depends(get_hq)):
        """How fast a stock goes (last 30 days of its history): per day, days left, last delivery."""
        need_ha(hq)
        if entity_id not in hq.watcher.states:
            raise HTTPException(404, tr("entità sconosciuta"))
        try:
            raw = (await hq.ha.history([entity_id], 24 * 30)).get(entity_id, [])
        except HomeAssistantError as exc:
            raise HTTPException(502, str(exc))
        return stock_stats(raw, datetime.now().astimezone())

    @app.post("/api/casa/entities/{entity_id}/stock", dependencies=[Depends(full)])
    async def casa_stock_set(entity_id: str, body: StockIn, hq: HQ = Depends(get_hq)):
        need_ha(hq)
        if entity_id not in hq.watcher.states:
            raise HTTPException(404, tr("entità sconosciuta"))
        await hq.casa.set_stock(entity_id, body.delivery, body.low)
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    @app.get("/api/casa/energy", dependencies=[Depends(auth)])
    async def casa_energy(hq: HQ = Depends(get_hq)):
        """The energy panel's live part: the time band now and today's power by band."""
        need_ha(hq)
        cfg = hq.casa.energy_config()
        now = datetime.now(hq.tz)
        out: dict = {"band": None, "day": None}
        if cfg["band_mode"] == "arera":
            band, until = band_until(now)
            out["band"] = {"name": band, "until": until.strftime("%H:%M"), "tomorrow": until.date() != now.date()}
        power = cfg["power"]
        if power and power in hq.watcher.states:
            hours = int((now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() // 3600) + 2
            try:
                raw = await hq.ha.history([power], hours)
            except HomeAssistantError as exc:
                raise HTTPException(502, str(exc))
            unit = (hq.watcher.states[power].get("attributes") or {}).get("unit_of_measurement") or "W"
            out["day"] = day_profile(raw.get(power, []), now, unit)
        return out

    @app.post("/api/casa/energy/config", dependencies=[Depends(full)])
    async def casa_energy_config(body: dict, hq: HQ = Depends(get_hq)):
        need_ha(hq)
        cfg = await hq.casa.set_energy_config(body)
        hq.emit({"type": "casa_changed"})
        return cfg

    @app.get("/api/casa/entities", dependencies=[Depends(full)])
    async def casa_entities(q: str = "", area: str | None = None, all: bool = False, hq: HQ = Depends(get_hq)):
        need_ha(hq)
        return hq.casa.candidates(q, area, include_here=all)

    @app.post("/api/casa/rooms/{area_id}/entities", dependencies=[Depends(full)])
    async def casa_add(area_id: str, body: RoomEntityIn, hq: HQ = Depends(get_hq)):
        need_ha(hq)
        if area_id not in hq.watcher.areas:
            raise HTTPException(404, tr("area sconosciuta"))
        if body.entity_id not in hq.watcher.states:
            raise HTTPException(404, tr("entità sconosciuta"))
        if body.mode == "ha":
            try:
                await hq.watcher.set_area(body.entity_id, area_id)
            except HAWatcherError as exc:
                raise HTTPException(409, str(exc))
            await hq.casa.moved_in_ha(area_id, body.entity_id)
        else:
            await hq.casa.show_here(area_id, body.entity_id)
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    @app.post("/api/casa/entities/{entity_id}/kind", dependencies=[Depends(full)])
    async def casa_kind(entity_id: str, body: KindIn, hq: HQ = Depends(get_hq)):
        need_ha(hq)
        if entity_id not in hq.watcher.states:
            raise HTTPException(404, tr("entità sconosciuta"))
        await hq.casa.set_kind(entity_id, body.kind)
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    @app.post("/api/casa/rooms/{area_id}/cards", dependencies=[Depends(full)])
    async def casa_card(area_id: str, body: CardIn, hq: HQ = Depends(get_hq)):
        """A card composed in "Modifica stanza" (e.g. the stove: switch, start and stop time)."""
        need_ha(hq)
        if area_id not in hq.watcher.areas:
            raise HTTPException(404, tr("area sconosciuta"))
        if body.kind == "free":
            if not body.blocks:
                raise HTTPException(422, tr("aggiungi almeno un blocco"))
            # its entities are those of its blocks (a text block has none)
            body.entities = list(dict.fromkeys(
                e for b in body.blocks
                for e in (b.entity, b.entity2, b.show.e if b.show else "", b.tap.e if b.tap else "") if e
            ))
        elif not body.entities:
            raise HTTPException(422, tr("aggiungi almeno un'entità"))
        unknown = [e for e in body.entities if e not in hq.watcher.states]
        if unknown:
            raise HTTPException(422, f"{tr('entità sconosciute')}: {', '.join(unknown)}")
        if body.enable and body.enable not in body.entities:
            raise HTTPException(422, tr("l'interruttore degli orari deve essere nella card"))
        card_id = await hq.casa.save_card(
            area_id, body.id, body.name, body.entities, body.size, body.group, body.enable, body.nochart,
            blocks=[{k: v for k, v in b.model_dump(exclude_none=True).items() if v != []} for b in body.blocks] if body.kind == "free" else None,
            color=body.color, style=body.style,
        )
        hq.emit({"type": "casa_changed"})
        return {"ok": True, "id": card_id}

    @app.post("/api/casa/rooms/{area_id}/cards/draft", dependencies=[Depends(full)])
    async def casa_card_draft(area_id: str, body: DraftIn, hq: HQ = Depends(get_hq)):
        """A free card described in words: Claude composes it with the house's real entities.
        It comes back for the editor; nothing is saved until the owner does."""
        from hubnex.cardgen import CARD_SCHEMA, SYSTEM, card_prompt, entity_lines

        need_ha(hq)
        area = hq.watcher.areas.get(area_id)
        if area is None:
            raise HTTPException(404, tr("area sconosciuta"))
        rooms = [(a, v.get("name") or a) for a, v in hq.watcher.areas.items()]
        prompt = card_prompt(area.get("name") or area_id, entity_lines(hq.casa, area_id), body.text, rooms)
        try:
            raw = await complete(hq.client, model=hq.settings.model, system=SYSTEM, prompt=prompt, effort="low",
                                 schema=CARD_SCHEMA, on_usage=hq.usage_for("cards"))
            data = json.loads(raw)
        except Exception as exc:
            raise HTTPException(502, f"{tr('card non riuscita')}: {exc}")
        return clean_card(hq, data, keep_missing=False)

    @app.post("/api/casa/cards/import", dependencies=[Depends(full)])
    async def casa_card_import(body: dict, hq: HQ = Depends(get_hq)):
        """A card shared as text (Esporta): its blocks for the editor; the entities this house
        doesn't have are left empty, to be chosen."""
        need_ha(hq)
        if not isinstance(body, dict) or body.get("hubnex_card") != 1 or not isinstance(body.get("blocks"), list):
            raise HTTPException(422, tr("non è una card di HubNEX"))
        return clean_card(hq, body, keep_missing=True)

    @app.post("/api/casa/rooms/{area_id}/cards/{card_id}/remove", dependencies=[Depends(full)])
    async def casa_card_delete(area_id: str, card_id: str, hq: HQ = Depends(get_hq)):
        need_ha(hq)
        await hq.casa.delete_card(area_id, card_id)
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    @app.post("/api/casa/rooms/{area_id}/order", dependencies=[Depends(full)])
    async def casa_order(area_id: str, body: OrderIn, hq: HQ = Depends(get_hq)):
        need_ha(hq)
        if area_id not in hq.watcher.areas:
            raise HTTPException(404, tr("area sconosciuta"))
        await hq.casa.set_order(area_id, body.items)
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    @app.post("/api/casa/entities/{entity_id}/display", dependencies=[Depends(full)])
    async def casa_display(entity_id: str, body: DisplayIn, hq: HQ = Depends(get_hq)):
        """Rename or resize an entity's card in HubNEX only."""
        need_ha(hq)
        if entity_id not in hq.watcher.states:
            raise HTTPException(404, tr("entità sconosciuta"))
        sent = body.model_fields_set
        await hq.casa.set_display(entity_id, body.name, body.size, rename="name" in sent, resize="size" in sent, chart=body.chart)
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    @app.post("/api/casa/rooms/{area_id}/temperature", dependencies=[Depends(full)])
    async def casa_temperature(area_id: str, body: RoomTempIn, hq: HQ = Depends(get_hq)):
        need_ha(hq)
        if area_id not in hq.watcher.areas:
            raise HTTPException(404, tr("area sconosciuta"))
        await hq.casa.set_temperature(area_id, body.entity_id)
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    @app.post("/api/casa/rooms/{area_id}/entities/{entity_id}/remove", dependencies=[Depends(full)])
    @app.delete("/api/casa/rooms/{area_id}/entities/{entity_id}", dependencies=[Depends(full)])
    async def casa_remove(area_id: str, entity_id: str, hq: HQ = Depends(get_hq)):
        """Taken off this room in the dashboard only: Home Assistant is left as it is."""
        need_ha(hq)
        await hq.casa.hide(area_id, entity_id)
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    @app.get("/api/casa/layout", dependencies=[Depends(full)])
    async def casa_layout(hq: HQ = Depends(get_hq)):
        return {"text": hq.casa.layout_text(), "error": hq.casa.layout_error, "file": hq.casa.host_path(),
                "areas": sorted(a.get("name") or k for k, a in hq.watcher.areas.items())}

    @app.post("/api/casa/layout", dependencies=[Depends(full)])
    @app.put("/api/casa/layout", dependencies=[Depends(full)])
    async def casa_save_layout(body: LayoutIn, hq: HQ = Depends(get_hq)):
        try:
            hq.casa.save_layout(body.text)
        except LayoutError as exc:
            raise HTTPException(422, str(exc))
        rooms = sum(len(f["rooms"]) for f in hq.casa.layout["floors"])
        await hq.log("system", tr_sys("Piantina della casa salvata: {n} stanze in {path}", n=rooms, path=hq.casa.host_path()))
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    @app.get("/api/casa/plan", dependencies=[Depends(full)])
    async def casa_plan(hq: HQ = Depends(get_hq)):
        """The floor plan as data, for the visual editor."""
        hq.casa.layout_text()
        return {**hq.casa.layout, "error": hq.casa.layout_error,
                "areas": sorted(a.get("name") or k for k, a in hq.watcher.areas.items())}

    @app.post("/api/casa/plan", dependencies=[Depends(full)])
    async def casa_plan_save(body: PlanIn, hq: HQ = Depends(get_hq)):
        try:
            hq.casa.save_layout_data(body.model_dump())
        except LayoutError as exc:
            raise HTTPException(422, str(exc))
        rooms = sum(len(f.rooms) for f in body.floors)
        await hq.log("system", tr_sys("Piantina della casa salvata dall'editor: {n} stanze", n=rooms))
        hq.emit({"type": "casa_changed"})
        return {"ok": True}

    # ------------------------------------------------------------------ backup and restore
    @app.get("/api/backup", dependencies=[Depends(full)])
    async def backup_download():
        """Everything HubNEX knows, in one zip (the add-on's options and keys excluded)."""
        data = await asyncio.to_thread(make_backup, settings.db_path, config_dir(settings), __version__)
        name = f"hubnex-backup-{datetime.now():%Y%m%d-%H%M}.zip"
        return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/backup/restore", dependencies=[Depends(full)])
    async def backup_restore(request: Request, hq: HQ = Depends(get_hq)):
        """A backup zip (raw body): set aside and applied at the next start."""
        try:
            manifest = await asyncio.to_thread(stage_restore, await request.body(), settings.db_path)
        except BackupError as exc:
            raise HTTPException(422, str(exc))
        await hq.log("system", tr_sys("Backup caricato: viene applicato al riavvio di HubNEX."))
        restarting = bool(os.environ.get("SUPERVISOR_TOKEN"))
        if restarting:
            asyncio.create_task(restart_addon())
        return {"ok": True, "manifest": manifest, "restarting": restarting}

    @app.post("/api/casa/plan-image", dependencies=[Depends(full)])
    async def casa_plan_image_upload(request: Request, floor: int = 1, hq: HQ = Depends(get_hq)):
        """A photo, image or PDF of the plan (raw body)."""
        data = await request.body()
        try:
            name, aspect = await asyncio.to_thread(hq.casa.save_plan_image, max(1, min(floor, 10)), data)
        except LayoutError as exc:
            raise HTTPException(422, str(exc))
        return {"image": name, "aspect": aspect}

    @app.get("/api/casa/plan-image/{name}", dependencies=[Depends(auth)])
    async def casa_plan_image(name: str, hq: HQ = Depends(get_hq)):
        path = hq.casa.plan_image_path(name)
        if not path:
            raise HTTPException(404, tr("immagine non trovata"))
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})

    @app.post("/api/casa/plan-suggest", dependencies=[Depends(full)])
    async def casa_plan_suggest(body: SuggestIn, hq: HQ = Depends(get_hq)):
        """Claude looks at the plan and proposes the rooms (to check in the editor)."""
        path = hq.casa.plan_image_path(body.image)
        if not path:
            raise HTTPException(404, tr("carica prima la planimetria"))
        areas = sorted(a.get("name") or k for k, a in hq.watcher.areas.items())
        image = base64.b64encode(path.read_bytes()).decode()
        try:
            raw = await complete(
                hq.client,
                model=hq.settings.model,
                system="Leggi planimetrie di abitazioni e ne ricavi i contorni delle stanze.",
                prompt=[
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image}},
                    {"type": "text", "text": suggest_prompt(areas)},
                ],
                effort="medium",
                schema=SUGGEST_SCHEMA,
                on_usage=hq.usage_for("plan"),
            )
            rooms, skipped = clean_suggestion(json.loads(raw), areas)
            if not rooms:
                raise ValueError("nessuna stanza valida nella proposta")
        except Exception as exc:
            raise HTTPException(502, f"{tr('proposta non riuscita')}: {exc}")
        await hq.log("system", tr_sys("Proposta della piantina: {n} stanze riconosciute", n=len(rooms)))
        return {"rooms": rooms, "skipped": skipped}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        try:
            check_token(websocket.query_params.get("token"), websocket.client.host if websocket.client else None)
        except HTTPException:
            await websocket.close(code=4401)
            return
        role = await role_of(websocket.client.host if websocket.client else None, websocket.headers)
        await websocket.accept()
        hq: HQ = websocket.app.state.hq
        queue = hq.subscribe()
        try:
            state = await hq.snapshot()
            await websocket.send_json({"type": "snapshot", "state": state if role == "full" else house_only(state)})
            while True:
                event = await queue.get()
                if role == "full" or event.get("type") in HOUSE_EVENTS:
                    await websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hq.unsubscribe(queue)

    return app


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    run()
