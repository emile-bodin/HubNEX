import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from hubnex.config import Routine
from hubnex.main import create_app
from hubnex.scheduler import Scheduler, is_due_at, parse_due, parse_interval
from tests.conftest import response, text_block, tool_block


def test_org_chart_loads():
    from hubnex.config import load_org

    org = load_org("config/agents.yaml")
    assert {c.id for c in org.companies} == {"home", "work"}
    assert org.agent("accountant").department == "admin"


def test_intervals_and_daily_routines():
    assert parse_interval("30m") == 1800
    assert parse_interval("6h") == 21600
    with pytest.raises(ValueError):
        parse_interval("ogni tanto")
    r = Routine(task="x", at="08:30", days=["mon", "tue", "wed", "thu", "fri"])
    monday_9 = datetime(2026, 10, 26, 9, 0)
    assert is_due_at(r, monday_9, None)
    assert not is_due_at(r, monday_9, date(2026, 10, 26))  # already ran today
    assert not is_due_at(r, datetime(2026, 10, 26, 8, 0), None)  # too early
    assert not is_due_at(r, datetime(2026, 10, 25, 9, 0), None)  # sunday


def test_parse_due_date_only_means_nine_am():
    tz = ZoneInfo("Europe/Rome")
    assert parse_due("2026-11-30", tz).hour == 9


async def test_agent_runs_tools_and_reports(make_hq):
    hq = make_hq(
        [
            response([tool_block("memory_save", {"topic": "IVA", "content": "trimestrale"})], "tool_use"),
            response([text_block("Fatto: ho salvato la periodicità IVA.")], "end_turn"),
        ]
    )
    events = hq.subscribe()
    result = await hq.run_agent("accountant", "Ricorda che l'IVA è trimestrale")

    assert result == "Fatto: ho salvato la periodicità IVA."
    assert hq.agents["accountant"].status == "sleeping"
    assert hq.agents["accountant"].done == 1
    assert (await hq.store.recall("IVA", "work"))[0]["content"] == "trimestrale"

    # The tool result went back to Claude in a single user message after the assistant turn.
    second = hq.client.requests[1]["messages"]
    assert second[-1]["content"][0]["type"] == "tool_result"
    assert "is_error" not in second[-1]["content"][0]

    statuses = []
    while not events.empty():
        ev = events.get_nowait()
        if ev["type"] == "agent":
            statuses.append(ev["agent"]["status"])
    assert "working" in statuses and statuses[-1] == "sleeping"


async def test_tools_outside_agent_allowlist_are_refused(make_hq):
    # The Sentinella can only observe: ha_call_service is not in its tools.
    hq = make_hq(
        [
            response([tool_block("ha_call_service", {"domain": "lock", "service": "unlock"})], "tool_use"),
            response([text_block("Non posso.")], "end_turn"),
        ]
    )
    await hq.run_agent("sentinel", "Apri la porta")
    result = hq.client.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert "non disponibile" in result["content"]


async def test_blocked_ha_services_never_reach_home_assistant():
    from hubnex.integrations.homeassistant import HomeAssistant, HomeAssistantError

    ha = HomeAssistant("http://ha.invalid", "t", {"lock.unlock"})
    with pytest.raises(HomeAssistantError, match="bloccato"):
        await ha.call_service("lock", "unlock", {"entity_id": "lock.porta"})
    await ha.close()


async def test_jarvis_delegates_and_keeps_chat_history(make_hq):
    hq = make_hq(
        [
            response([tool_block("delegate", {"agent_id": "sales", "task": "Prepara un preventivo", "wait": True})], "tool_use"),
            response([text_block("Ecco il preventivo!")], "end_turn"),  # commerciale
            response([text_block("Il preventivo è pronto, signore.")], "end_turn"),  # jarvis
            response([text_block("Prego.")], "end_turn"),
        ]
    )
    reply = await hq.chat("test", "Fammi un preventivo")
    assert reply == "Il preventivo è pronto, signore."
    assert hq.agents["sales"].last_result == "Ecco il preventivo!"

    await hq.chat("test", "Grazie")
    msgs = hq.client.requests[-1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"] == "Il preventivo è pronto, signore."


async def test_deadline_warning_sent_once(make_hq):
    hq = make_hq([])
    await hq.store.deadline_add("F24", "2026-10-27")
    sent = []

    async def fake_notify(text):
        sent.append(text)

    hq.notify = fake_notify
    sched = Scheduler(hq)
    now = datetime(2026, 10, 26, 18, 0, tzinfo=hq.tz)
    await sched.check_deadlines(now)
    await sched.check_deadlines(now)
    assert len(sent) == 1 and "F24" in sent[0]


def test_api_requires_token(settings, make_hq):
    settings.hq_token = "segreto"
    app = create_app(settings, hq=make_hq([]), start_workers=False)
    with TestClient(app) as client:
        assert client.get("/api/state").status_code == 401
        r = client.get("/api/state", headers={"Authorization": "Bearer segreto"})
        assert r.status_code == 200
        assert len(r.json()["agents"]) == 7  # 6 agents + Jarvis
        assert client.get("/").status_code == 200
        with client.websocket_connect("/ws?token=segreto") as ws:
            assert ws.receive_json()["type"] == "snapshot"


def test_api_post_endpoints_read_json_bodies(settings, make_hq):
    hq = make_hq([response([text_block("Scadenza registrata.")], "end_turn")])
    app = create_app(settings, hq=hq, start_workers=False)
    with TestClient(app) as client:
        r = client.post("/api/deadlines", json={"title": "F24", "due": "2026-11-16"})
        assert r.status_code == 200
        assert client.post("/api/deadlines", json={"title": "x", "due": "domani"}).status_code == 422
        r = client.post("/api/agents/accountant/task", json={"task": "Controlla le scadenze", "wait": True})
        assert r.json() == {"result": "Scadenza registrata."}
        assert client.post("/api/agents/nessuno/task", json={"task": "x"}).status_code == 404
        assert client.get("/api/state").json()["deadlines"][0]["title"] == "F24"


def test_addon_loader(tmp_path, monkeypatch):
    import json
    import os

    from hubnex.config import _load_addon_options

    for var in ["ANTHROPIC_API_KEY", "TELEGRAM_ALLOWED_CHATS", "HA_URL", "HA_TOKEN", "HUBNEX_DB",
                "HUBNEX_AGENTS_FILE", "TELEGRAM_VOICE_REPLIES"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sup-token")
    opts = tmp_path / "options.json"
    opts.write_text(json.dumps({"anthropic_api_key": "sk-test", "telegram_allowed_chats": "111,222",
                                "telegram_voice_replies": False, "hq_token": ""}))
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()

    assert _load_addon_options(str(opts), str(cfg_dir)) is True
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test"
    assert os.environ["TELEGRAM_VOICE_REPLIES"] == "false"
    assert os.environ["HA_URL"] == "http://supervisor/core"
    assert os.environ["HA_TOKEN"] == "sup-token"
    assert (cfg_dir / "agents.yaml").exists()  # default org chart copied for editing
    assert os.environ["HUBNEX_AGENTS_FILE"] == str(cfg_dir / "agents.yaml")
    assert _load_addon_options(str(tmp_path / "missing.json"), str(cfg_dir)) is False


def test_addon_without_token_only_allows_ingress(settings, make_hq):
    settings.trusted_proxy = "testclient"  # TestClient's client host plays the ingress proxy
    app = create_app(settings, hq=make_hq([]), start_workers=False)
    with TestClient(app) as client:
        assert client.get("/api/ping").status_code == 200
    settings.trusted_proxy = "172.30.32.2"
    app = create_app(settings, hq=make_hq([]), start_workers=False)
    with TestClient(app) as client:
        assert client.get("/api/ping").status_code == 401


def test_older_activity_is_paged(settings, make_hq):
    import asyncio

    hq = make_hq([])

    async def seed():
        for i in range(30):
            await hq.store.log("system", f"evento {i}")

    asyncio.run(seed())
    app = create_app(settings, hq=hq, start_workers=False)
    with TestClient(app) as client:
        newest = client.get("/api/logs?limit=10").json()
        assert [e["text"] for e in newest][-1] != "evento 0" and len(newest) == 10
        older = client.get(f"/api/logs?before={newest[0]['id']}&limit=10").json()
        assert len(older) == 10 and older[-1]["id"] == newest[0]["id"] - 1


async def test_routines_are_off_unless_switched_on(make_hq):
    from hubnex.config import load_org

    org = load_org("config/agents.yaml")
    assert all(not r.enabled for a in org.agents for r in a.routines)  # shipped switched off
    hq = make_hq([])
    hq.org.agent("butler").routines = [Routine(task="spento", at="00:00"), Routine(task="acceso", at="00:00", enabled=True)]
    fired = []
    sched = Scheduler(hq)
    sched._last_at.clear()  # pretend the slot hasn't passed yet today
    sched._fire = lambda agent_id, r: fired.append(r.task)
    await sched.tick()
    assert fired == ["acceso"]


async def test_routines_and_events_cannot_act_on_the_house(make_hq, settings):
    calls = []

    class FakeHA:
        enabled = True

        async def call_service(self, domain, service, data):
            calls.append((domain, service))
            return []

    hq = make_hq(
        [
            response([tool_block("ha_call_service", {"domain": "light", "service": "turn_off"})], "tool_use"),
            response([text_block("La luce è accesa, la spengo?")], "end_turn"),
            response([tool_block("ha_call_service", {"domain": "light", "service": "turn_off"})], "tool_use"),
            response([text_block("Fatto.")], "end_turn"),
        ]
    )
    hq.ha = FakeHA()
    hq.run_agent_background("butler", "Controllo serale", source="routine", report=False)
    await asyncio.gather(*hq._background)
    result = hq.client.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "non l'ha chiesto" in result["content"]
    assert calls == []
    # The same agent, asked by the owner, can do it.
    await hq.run_agent("butler", "Spegni la luce del salotto")
    assert calls == [("light", "turn_off")]


async def test_owner_rules_bind_the_whole_team(make_hq):
    hq = make_hq(
        [
            response([tool_block("owner_rules", {"action": "add", "rule": "Nessuna iniziativa senza un mio ordine esplicito."})], "tool_use"),
            response([text_block("Registrato, Signore.")], "end_turn"),
            response([text_block("ok")], "end_turn"),
        ]
    )
    await hq.chat("dashboard", "D'ora in poi niente iniziative senza un mio ordine")
    assert hq.rules == ["Nessuna iniziativa senza un mio ordine esplicito."]
    await hq.run_agent("butler", "Che luci sono accese?")
    assert "1. Nessuna iniziativa senza un mio ordine esplicito." in hq.client.requests[2]["system"]
    await hq.load()  # survives a restart
    assert hq.rules == ["Nessuna iniziativa senza un mio ordine esplicito."]


def test_automation_events_can_only_report(settings, make_hq):
    calls = []

    class FakeHA:
        enabled = True

        async def call_service(self, domain, service, data):
            calls.append(domain)
            return []

        async def close(self):
            pass

    hq = make_hq(
        [
            response([tool_block("ha_call_service", {"domain": "light", "service": "turn_off"})], "tool_use"),
            response([text_block("Porta aperta da 10 minuti.")], "end_turn"),
        ]
    )
    hq.ha = FakeHA()
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        r = client.post("/api/ha/event", json={"message": "porta aperta", "notify": False})
    assert r.json()["reply"] == "Porta aperta da 10 minuti." and calls == []


async def test_spoken_summary_only_when_asked(make_hq, settings):
    long = "Le verifiche sono:\n- isolamento: annuale\n- differenziali: annuale"
    hq = make_hq(
        [
            response([text_block(long + "\n[VOCE] Signore, sono quasi tutte annuali: il dettaglio è qui sotto.")], "end_turn"),
            response([text_block(long + "\n[VOCE]: Il dettaglio è qui sotto.")], "end_turn"),
            response([text_block("Fatto, Signore.")], "end_turn"),
        ]
    )
    # "completa" (default): no request for a summary, a stray [VOCE] line is still removed
    assert await hq.converse("t", "verifiche?", spoken=True) == (long, None, "jarvis")
    assert "[VOCE]" not in hq.client.requests[-1]["messages"][-1]["content"]

    settings.voice_answers = "riassunto"
    written, said, _ = await hq.converse("t", "verifiche?", spoken=True)
    assert written == long and said == "Il dettaglio è qui sotto."
    assert "[VOCE]" in hq.client.requests[-1]["messages"][-1]["content"]
    # a short answer has nothing to summarise: the voice reads it whole
    assert await hq.converse("t", "spegni", spoken=True) == ("Fatto, Signore.", None, "jarvis")


def test_split_voice():
    from hubnex.speech import split_voice

    assert split_voice("Testo.\n\n[VOCE] Breve.") == ("Testo.", "Breve.")
    assert split_voice("Solo testo.") == ("Solo testo.", None)


def _house(hq, local=None):
    asked = []

    class HA:
        enabled = True

        async def conversation(self, text, agent_id="conversation.home_assistant"):
            asked.append(text)
            return local or {"response": {"response_type": "error", "data": {"code": "no_intent_match"}}}

    hq.ha = HA()
    w = hq.watcher
    w.areas = {"cucina": {"area_id": "cucina", "name": "Cucina"}}
    w.entities = {"light.cucina": {"entity_id": "light.cucina", "area_id": "cucina", "aliases": ["Luce cucina"]},
                  "sensor.cpu": {"entity_id": "sensor.cpu", "entity_category": "diagnostic"}}
    w.states = {
        "light.cucina": {"entity_id": "light.cucina", "state": "off", "attributes": {"friendly_name": "Lampada"}},
        "sensor.temp_cucina": {"entity_id": "sensor.temp_cucina", "state": "21.5", "attributes": {"device_class": "temperature", "unit_of_measurement": "°C"}},
        "sensor.cpu": {"entity_id": "sensor.cpu", "state": "3", "attributes": {}},
        "automation.x": {"entity_id": "automation.x", "state": "on", "attributes": {}},
    }
    return asked


async def test_assist_house_request_takes_the_quick_route(make_hq):
    hq = make_hq([response([text_block("Fatto, Signore.")], "end_turn")])
    asked = _house(hq)
    assert await hq.converse("assist", "accendi la luce della cucina", voice=True, quick=True) == ("Fatto, Signore.", None, "quick")
    assert asked == []  # Assist already tried Home Assistant's sentences
    req = hq.client.requests[-1]
    assert req["model"] == "claude-haiku-5-5" and "IL TUO TEAM" not in req["system"]
    last = req["messages"][-1]["content"]
    assert "light.cucina · Luce cucina · Cucina · off" in last and "21.5 °C" in last
    assert "sensor.cpu" not in last and "automation.x" not in last
    assert {t.get("name") for t in req.get("tools", [])} <= {"ha_list_entities", "ha_get_state", "ha_call_service"}
    assert all("Casa adesso" not in h["text"] for h in await hq.store.chat_history("assist", 10))


async def test_complex_request_goes_to_jarvis(make_hq):
    hq = make_hq([response([text_block("[[JARVIS]]")], "end_turn"),
                  response([text_block("Le verifiche annuali sono tre, Signore.")], "end_turn")])
    _house(hq)
    reply, _, by = await hq.converse("assist", "quali verifiche servono in un locale di gruppo 2?", voice=True, quick=True)
    assert by == "jarvis" and reply.startswith("Le verifiche")
    quick_req, full_req = hq.client.requests[-2:]
    assert quick_req["model"] == "claude-haiku-5-5"
    assert full_req["model"] == hq.settings.model and "IL TUO TEAM" in full_req["system"]
    # the history has the question once and Jarvis' answer, not the hand-over
    texts = [h["text"] for h in await hq.store.chat_history("assist", 10)]
    assert texts == ["quali verifiche servono in un locale di gruppo 2?", "Le verifiche annuali sono tre, Signore."]


async def test_dashboard_tries_home_assistant_first(make_hq):
    hq = make_hq([])
    asked = _house(hq, {"response": {"response_type": "action_done", "speech": {"plain": {"speech": "Luce accesa"}}}})
    out = await hq.converse("dashboard", "[Sono nella stanza Cucina della vista Casa] accendi la luce", quick=True, local=True)
    assert out == ("Luce accesa", None, "ha") and asked == ["accendi la luce"] and hq.client.requests == []
    # locks and the alarm never go through Home Assistant's sentences nor the quick route
    hq2 = make_hq([response([text_block("Mi conferma che devo sbloccare la porta, Signore?")], "end_turn")])
    asked2 = _house(hq2, {"response": {"response_type": "action_done", "speech": {"plain": {"speech": "Sbloccata"}}}})
    reply, _, by = await hq2.converse("dashboard", "sblocca la porta d'ingresso", quick=True, local=True)
    assert by == "jarvis" and asked2 == [] and hq2.client.requests[-1]["model"] == hq2.settings.model


def test_mail_ignore_list(settings):
    from hubnex.maildesk import MailDesk

    settings.mail_ignore = ("@newsletter.it", "offerte@negozio.it", "noreply")
    desk = MailDesk.__new__(MailDesk)
    desk.settings = settings
    assert desk.ignored("Newsletter <news@newsletter.it>")
    assert desk.ignored("offerte@negozio.it")
    assert desk.ignored("Banca <NoReply@banca.it>")
    assert not desk.ignored("Mario Rossi <mario@negozio.it>")
    assert not desk.ignored("cliente@newsletter.it.example.com")
