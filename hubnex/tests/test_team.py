"""The merged Jarvis Mail behaviour: Telegram group, drafts, mailbox check, per-agent models."""

import json
from email.message import EmailMessage

from hubnex.context import CURRENT_CHAT
from hubnex.maildesk import MailDesk
from tests.conftest import FakeTeam, response, text_block, tool_block

ORIGINAL = {
    "uid": 42, "da": "Cliente <cliente@example.com>", "a": "io@example.com", "cc": "",
    "oggetto": "Sopralluogo", "data": "26/10/2026 09:00", "message_id": "<m1@example.com>",
    "references": "", "reply_to": "", "allegati": [], "testo": "Quando venite?",
}


class FakeMail:
    def __init__(self):
        self.sent = []
        self.saved = []
        self.uid_next = 100
        self.new = []

    def get_email(self, uid):
        return dict(ORIGINAL, uid=uid)

    def build_reply(self, original, body, reply_all=False):
        msg = EmailMessage()
        msg["To"] = original["da"]
        msg["Cc"] = ""
        msg["Subject"] = "Re: " + original["oggetto"]
        msg.set_content(body)
        return msg

    def send(self, msg):
        self.sent.append(msg)

    def save_draft(self, msg):
        self.saved.append(msg)
        return "Bozze"

    def mailbox_state(self):
        return 1, self.uid_next - 1

    def new_since(self, last_uid):
        return [e for e in self.new if e["uid"] > last_uid]


def with_mail(hq):
    desk = MailDesk(hq)
    desk.client = FakeMail()
    hq.maildesk = desk
    return desk


def test_mail_agent_uses_mail_model_and_haiku_rules(make_hq):
    hq = make_hq([response([text_block("Nessuna email nuova.")], "end_turn")])
    hq.settings.model_mail = "claude-haiku-5-5"
    assert hq.model_for(hq.org.agent("mail")) == "claude-haiku-5-5"
    assert hq.model_for(hq.org.agent("technical")) == hq.settings.model == "claude-sonnet-5-5"
    assert hq._tool_defs(["web_search"], "claude-haiku-5-5")[0]["type"] == "web_search_20250305"
    assert hq._tool_defs(["web_search"], "claude-sonnet-5-5")[0]["type"] == "web_search_20260209"


async def test_web_searches_per_request_are_set_per_agent(make_hq, tmp_path):
    import pytest
    import yaml

    from hubnex.config import load_org

    data = yaml.safe_load(open("config/agents.yaml", encoding="utf-8"))
    data["boss"]["max_searches"] = 2
    tecnico = next(a for c in data["companies"] for a in c["agents"] if a["id"] == "technical")
    tecnico["max_searches"] = 3
    path = tmp_path / "agents.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    hq = make_hq([response([text_block("ok")], "end_turn")] * 2)
    hq.org = load_org(str(path))
    assert await hq.run_agent("technical", "cerca") == "ok"
    tools = {t["name"]: t for t in hq.client.requests[0]["tools"]}
    assert tools["web_search"]["max_uses"] == 3 and tools["web_fetch"]["max_uses"] == 5
    await hq.chat("dashboard", "cerca")
    assert next(t for t in hq.client.requests[1]["tools"] if t["name"] == "web_search")["max_uses"] == 2
    assert hq.org.agent("mail").max_searches == 5  # not set: as before
    tecnico["max_searches"] = 0
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="max_searches"):
        load_org(str(path))


async def test_haiku_requests_have_no_server_fallback(make_hq):
    hq = make_hq([response([text_block("ok")], "end_turn"), response([text_block("ok")], "end_turn")])
    await hq.run_agent("mail", "Ci sono email?")
    await hq.run_agent("technical", "Che norma vale per gli idranti?")
    haiku, sonnet = hq.client.requests
    assert haiku["model"] == "claude-haiku-5-5" and "fallbacks" not in haiku
    assert sonnet["model"] == "claude-sonnet-5-5" and sonnet["fallbacks"] == "default"


async def test_in_the_group_the_agent_answers_and_jarvis_stays_silent(make_hq):
    team = FakeTeam()
    hq = make_hq(
        [
            response([tool_block("delegate", {"agent_id": "mail", "task": "Email importanti?", "wait": True})], "tool_use"),
            response([text_block("Due email importanti: ...")], "end_turn"),  # Jarvis Mail
            response([text_block("[[SILENZIO]]")], "end_turn"),  # Jarvis
        ],
        team=team,
    )
    CURRENT_CHAT.set(-100)
    reply = await hq.chat("telegram:-100", "Ci sono email importanti?")
    assert reply == ""
    assert team.posts == [{"agent": "mail", "text": "Due email importanti: ...", "chat": -100, "buttons": None}]
    delegate_result = json.loads(hq.client.requests[2]["messages"][-1]["content"][0]["content"])
    assert delegate_result["gia_mostrato_all_utente"] is True


async def test_draft_needs_two_clicks_to_send(make_hq):
    team = FakeTeam()
    hq = make_hq([], team=team)
    desk = with_mail(hq)
    CURRENT_CHAT.set(-100)

    msg = await desk.propose_draft(42, "Veniamo giovedì.", False)
    assert "NON è stata inviata" in msg
    post = team.posts[-1]
    assert post["agent"] == "mail" and "DRAFT #1" in post["text"]
    assert [b[1] for b in post["buttons"][0]] == ["d:1:ask", "d:1:save"]

    toasts, edits = [], []

    async def answer(text, alert):
        toasts.append(text)

    async def edit(buttons):
        edits.append(buttons)

    await desk.draft_action(1, "ask", answer, edit)
    assert desk.client.sent == []  # first click only asks for confirmation
    assert edits[-1][0][0][1] == "d:1:send"

    await desk.draft_action(1, "send", answer, edit)
    assert len(desk.client.sent) == 1
    assert (await hq.store.draft(1))["status"] == "sent"
    assert team.buttons[-1][1] is None  # buttons removed
    await desk.draft_action(1, "send", answer, edit)
    assert len(desk.client.sent) == 1 and toasts[-1] == "Draft no longer active"


async def test_mail_check_baseline_then_announces_new_mail(make_hq):
    team = FakeTeam()
    triage = json.dumps({"email": [{"uid": 100, "priorita": "alta", "riassunto": "Chiede un sopralluogo"}]})
    hq = make_hq([response([text_block(triage)], "end_turn")], team=team)
    desk = with_mail(hq)

    await desk.check()  # first run: remember where we are, announce nothing
    assert team.posts == [] and await hq.store.get("mail_last_uid") == 99

    desk.client.new = [{"uid": 100, "da": "Cliente <c@example.com>", "oggetto": "Sopralluogo", "data": "", "letta": False, "anteprima": ""}]
    await desk.check()
    post = team.posts[-1]
    assert post["agent"] == "mail" and "🔴 Cliente — Sopralluogo" in post["text"]
    assert post["buttons"][0][1][1] == "n:100:reply"
    assert await hq.store.get("mail_last_uid") == 100
    # The classifier got a JSON schema, and Jarvis was told about the new mail.
    assert hq.client.requests[0]["output_config"]["format"]["type"] == "json_schema"
    history = await hq.store.chat_history("telegram:-100")
    assert history[0]["text"].startswith("[nota dal gruppo] Jarvis Mail ha segnalato")


async def test_agents_without_a_bot_speak_through_jarvis(make_hq, settings):
    from types import SimpleNamespace as NS

    from hubnex.integrations.telegram import TelegramTeam

    class Bot:
        def __init__(self):
            self.sent = []

        async def send_message(self, chat_id, text, **kw):
            self.sent.append(text)
            return NS(message_id=len(self.sent))

    settings.telegram_chat_id = "-100"
    team = TelegramTeam.__new__(TelegramTeam)
    team.settings, team.hq = settings, make_hq([])
    team.apps = {"jarvis": NS(bot=Bot()), "mail": NS(bot=Bot())}

    await team.post("mail", "Nuova email")
    await team.post("technical", "Piano del giorno")
    await team.post(None, "Buongiorno")
    assert team.apps["mail"].bot.sent == ["Nuova email"]
    assert team.apps["jarvis"].bot.sent == ["Jarvis Technical:\nPiano del giorno", "Buongiorno"]


async def test_two_simultaneous_clicks_send_only_once(make_hq):
    import asyncio

    from hubnex.maildesk import DraftClosed

    hq = make_hq([], team=FakeTeam())
    desk = with_mail(hq)
    await desk.propose_draft(42, "Veniamo giovedì.", False, chat=-100)
    results = await asyncio.gather(desk.finish(1, "send"), desk.finish(1, "send"), return_exceptions=True)
    assert len(desk.client.sent) == 1
    assert sum(isinstance(r, DraftClosed) for r in results) == 1


def test_dashboard_drafts_api(settings, make_hq):
    from fastapi.testclient import TestClient

    from hubnex.main import create_app

    # No Telegram at all: drafts still reach the dashboard.
    hq = make_hq([response([text_block("Veniamo giovedì mattina, cordiali saluti.")], "end_turn")])
    desk = with_mail(hq)
    app = create_app(settings, hq=hq, start_workers=False)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["state"]["drafts"] == []
            client.portal.call(desk.propose_draft, 42, "Veniamo giovedì.", False)
            while (ev := ws.receive_json())["type"] != "drafts":
                pass
            assert ev["drafts"][0]["subject"] == "Re: Sopralluogo"

        r = client.post("/api/drafts/1/revise", json={"text": "più formale"})
        assert r.status_code == 200
        drafts = client.get("/api/state").json()["drafts"]
        assert [d["id"] for d in drafts] == [2] and "cordiali saluti" in drafts[0]["body"]

        assert client.post("/api/drafts/1/send").status_code == 409  # replaced, not sendable
        assert client.post("/api/drafts/2/bogus").status_code == 422
        r = client.post("/api/drafts/2/send")
        assert r.status_code == 200 and "sent at" in r.json()["note"]
        assert len(desk.client.sent) == 1
        assert client.post("/api/drafts/2/send").status_code == 409
        assert client.get("/api/state").json()["drafts"] == []


def test_html_signature_sends_formatted_email():
    from hubnex.config import MailSettings
    from hubnex.integrations.mail import MailClient

    sig = '<p><b>Anna Bianchi</b><br>Azienda Esempio srl<br><a href="https://example.com">example.com</a></p>'
    client = MailClient(MailSettings(user="io@example.com", password="x", signature=sig))
    msg = client.build_reply(ORIGINAL, "Veniamo giovedì.\nA presto.")
    assert msg.get_content_type() == "multipart/alternative"
    plain = msg.get_body(("plain",)).get_content()
    html_part = msg.get_body(("html",)).get_content()
    assert "<b>" not in plain and "Anna Bianchi" in plain and "Azienda Esempio srl" in plain
    assert sig in html_part and "Veniamo giovedì.<br>" in html_part
    assert "&gt;" not in html_part.split(sig)[0]  # body escaped, not broken

    # A plain-text signature keeps the old behaviour: a single text/plain email.
    plain_msg = MailClient(MailSettings(user="io@example.com", password="x", signature="Mario\\nMG")).build_reply(ORIGINAL, "Ok")
    assert plain_msg.get_content_type() == "text/plain"
    assert "Mario\nMG" in plain_msg.get_content()


async def test_jarvis_bot_routes_mail_and_house_buttons(make_hq, settings):
    """Without a Jarvis Mail bot the mail buttons reach Jarvis' bot: they must still work, and
    never be taken for the buttons of a house notification."""
    from types import SimpleNamespace as NS

    from hubnex.integrations.telegram import TelegramTeam

    team = TelegramTeam.__new__(TelegramTeam)
    team.settings, team.hq = settings, make_hq([])
    team.apps = {"jarvis": NS(bot=None)}
    team.allowed = lambda update: True
    routed, pressed = [], []

    def mail_handler(agent_id):
        async def handler(update, ctx):
            routed.append((agent_id, update.callback_query.data))
        return handler

    async def press(tok):
        pressed.append(tok)
        return "ok"

    team._agent_button_handler = mail_handler
    team.hq.alerts.press = press

    class Q:
        def __init__(self, data):
            self.data, self.message = data, NS(chat=NS(id=-100))

        async def answer(self, *a, **k):
            pass

        async def edit_message_reply_markup(self, *a, **k):
            pass

    await team.on_button_jarvis(NS(callback_query=Q("n:42:read")), None)
    await team.on_button_jarvis(NS(callback_query=Q("h:abc123")), None)
    assert routed == [("mail", "n:42:read")]
    assert pressed == ["abc123"]


def test_mail_buttons_have_no_emoji():
    import inspect

    src = inspect.getsource(MailDesk.check)
    assert "📖" not in src and "✍️" not in src
