"""Assist hookup: voice mode, the integration's token, installing and announcing the integration."""

import json

from fastapi.testclient import TestClient

from hubnex import addon
from hubnex.main import create_app
from tests.conftest import response, text_block


async def test_voice_answers_are_short_and_quick(make_hq):
    hq = make_hq([response([text_block("Fatto, signore.")], "end_turn")])
    await hq.chat("assist", "accendi la cucina", voice=True)
    req = hq.client.requests[0]
    assert req["output_config"]["effort"] == "low"
    assert "al massimo due frasi" in req["messages"][-1]["content"]
    # The history keeps what was actually said, not the voice hint.
    assert (await hq.store.chat_history("assist"))[0]["text"] == "accendi la cucina"


def test_integration_token_works_without_hq_token(settings, make_hq):
    settings.trusted_proxy = "172.30.32.2"  # add-on, no HQ token set
    settings.internal_token = "interno"
    hq = make_hq([response([text_block("Buonasera, signore.")], "end_turn")])
    app = create_app(settings, hq=hq, start_workers=False)
    with TestClient(app) as client:
        assert client.get("/api/ping").status_code == 401
        auth = {"Authorization": "Bearer interno"}
        assert client.get("/api/ping", headers=auth).json() == {"name": "Jarvis"}
        r = client.post("/api/chat", headers=auth, json={"text": "ciao", "channel": "assist", "voice": True})
        assert r.json() == {"reply": "Buonasera, signore.", "by": "jarvis"}


def test_the_dashboard_chat_answers_through_a_job(settings, make_hq):
    """A long answer must not hang on one request: the job id comes at once, the answer later."""
    import time as _time

    settings.hq_token = "t"
    hq = make_hq([response([text_block("Fatto, Signore.")], "end_turn")])
    hq.settings.model_voice = ""  # no quick route: straight to Jarvis
    app = create_app(settings, hq=hq, start_workers=False)
    auth = {"Authorization": "Bearer t"}
    with TestClient(app) as client:
        job = client.post("/api/chat", headers=auth, json={"text": "prepara la relazione", "background": True}).json()["job"]
        for _ in range(50):
            out = client.get(f"/api/chat/{job}", headers=auth).json()
            if out["done"]:
                break
            _time.sleep(0.05)
        assert out == {"done": True, "reply": "Fatto, Signore.", "by": "jarvis"}
        assert client.get(f"/api/chat/{job}", headers=auth).status_code == 404  # given once
        hq.client.responses = []  # the next call fails: the error comes back on the job
        job = client.post("/api/chat", headers=auth, json={"text": "di nuovo", "background": True}).json()["job"]
        for _ in range(50):
            r = client.get(f"/api/chat/{job}", headers=auth)
            if r.status_code != 200 or r.json()["done"]:
                break
            _time.sleep(0.05)
        assert r.status_code == 502


def test_integration_installed_once_and_updated_on_change(tmp_path):
    ha_config = tmp_path / "homeassistant"
    ha_config.mkdir()
    assert addon.install_integration(ha_config=ha_config) is True
    dest = ha_config / "custom_components" / "hubnex"
    assert json.loads((dest / "manifest.json").read_text())["domain"] == "hubnex"
    assert addon.install_integration(ha_config=ha_config) is False  # same version: no restart needed
    (dest / "const.py").write_text("# vecchia versione\n")
    assert addon.install_integration(ha_config=ha_config) is True
    assert "DOMAIN" in (dest / "const.py").read_text()
    assert addon.install_integration(ha_config=tmp_path / "manca") is False


async def test_announces_itself_to_home_assistant(monkeypatch):
    sent = {}

    class FakeClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json, headers):
            sent.update(url=url, json=json, headers=headers)
            return type("R", (), {"status_code": 200, "text": ""})()

    monkeypatch.setattr(addon.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(addon.socket, "gethostname", lambda: "local-hubnex")
    monkeypatch.setenv("SUPERVISOR_TOKEN", "sup")
    await addon.announce("interno", 8765)
    assert sent["url"] == "http://supervisor/discovery"
    assert sent["json"] == {"service": "hubnex", "config": {"host": "local-hubnex", "port": 8765, "token": "interno"}}
    assert sent["headers"] == {"Authorization": "Bearer sup"}


def test_call_cost_by_model():
    from types import SimpleNamespace as NS

    from hubnex.pricing import call_cost

    usage = NS(input_tokens=1_000_000, output_tokens=100_000, cache_read_input_tokens=1_000_000,
               cache_creation_input_tokens=0, server_tool_use=NS(web_search_requests=2))
    # Sonnet 5.5: 2$ in + 1$ out + 0.20$ cache read + 2 searches (0.02$)
    assert round(call_cost("claude-sonnet-5-5", usage), 4) == 3.22
    small = NS(input_tokens=10_000, output_tokens=1_000, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    assert round(call_cost("claude-haiku-5-5", small), 6) == 0.0015


async def test_credit_counts_down_and_resets_on_top_up(make_hq, settings):
    settings.anthropic_credit_usd = 1.05
    hq = make_hq([response([text_block("ok")], "end_turn")])
    sent = []

    async def notify(text, agent_id=None):
        sent.append(text)

    hq.notify = notify
    await hq.load()
    await hq.chat("dashboard", "ciao")  # FakeClient: 10 in / 5 out on Sonnet
    stats = await hq.stats()
    assert stats["credit_usd"] == 1.05 and 0 < stats["spent_usd"] < 0.001

    from types import SimpleNamespace as NS

    big = NS(input_tokens=30_000, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    await hq.on_usage(big, "claude-sonnet-5-5")  # +0.06$ -> below 1$ left
    await hq.on_usage(big, "claude-sonnet-5-5")
    assert len(sent) == 1 and "almost used up" in sent[0]  # warned once

    await hq.load()  # restart with the same credit: spend is kept
    assert (await hq.stats())["spent_usd"] > 0.1
    settings.anthropic_credit_usd = 5.0  # top-up entered in the configuration
    await hq.load()
    assert (await hq.stats())["spent_usd"] == 0


def test_version_matches_addon_manifest_and_dashboard_is_revalidated(settings, make_hq):
    import pathlib

    import yaml

    from hubnex import __version__

    manifest = yaml.safe_load((pathlib.Path(__file__).parent.parent / "config.yaml").read_text())
    assert manifest["version"] == __version__
    app = create_app(settings, hq=make_hq([]), start_workers=False)
    with TestClient(app) as client:
        assert client.get("/").headers["cache-control"] == "no-cache"
        assert client.get("/static/app.js").headers["cache-control"] == "no-cache"
        assert client.get("/api/state").json()["version"] == __version__


def test_addon_defaults_pass_supervisor_validation():
    """Supervisor rejects the whole configuration (the add-on won't start) when a default
    doesn't fit its type: an empty "" is not a valid url/email even when marked optional."""
    import pathlib

    import yaml

    manifest = yaml.safe_load((pathlib.Path(__file__).parent.parent / "config.yaml").read_text())
    for key, default in manifest["options"].items():
        kind = str(manifest["schema"][key]).rstrip("?")
        if default == "":
            assert kind.startswith(("str", "password")), f"{key}: '' is not a valid {kind}"
        if kind == "port":
            assert isinstance(default, int)


def test_voice_failures_are_explained(settings, make_hq):
    import httpx

    from hubnex.integrations.elevenlabs import ElevenLabs

    hq = make_hq([])
    hq.voice = ElevenLabs("chiave", "voce")
    hq.voice._client = httpx.AsyncClient(base_url="https://x", transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={"detail": {"status": "detected_unusual_activity", "message": "Free Tier usage disabled"}})))
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        r = client.post("/api/tts", json={"text": "Buonasera"})
        assert r.status_code == 502
        assert "free plan blocked" in r.json()["detail"] and "Free Tier usage disabled" in r.json()["detail"]
        feed = client.get("/api/logs").json()
        assert any("Voice not available" in e["text"] for e in (feed if isinstance(feed, list) else feed.get("logs", [])))


def test_voice_from_home_assistant_tts(settings, make_hq):
    settings.voice_tts_entity = "tts.piper"
    hq = make_hq([])
    asked = []

    class FakeHA:
        enabled = True

        async def tts(self, engine, text, language=None, options=None):
            asked.append((engine, text))
            return b"RIFFwav", "audio/wav"

        async def close(self):
            pass

    hq.ha = FakeHA()
    assert hq.tts_enabled  # no ElevenLabs needed
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        r = client.post("/api/tts", json={"text": "Buonasera"})
    assert r.content == b"RIFFwav" and r.headers["content-type"] == "audio/wav" and asked == [("tts.piper", "Buonasera.")]


async def test_home_assistant_tts_client():
    import httpx

    from hubnex.integrations.homeassistant import HomeAssistant

    def handler(r: httpx.Request):
        if r.url.path == "/api/tts_get_url":
            assert json.loads(r.content)["engine_id"] == "tts.piper"
            return httpx.Response(200, json={"url": "http://ha/api/tts_proxy/abc.mp3", "path": "/api/tts_proxy/abc.mp3"})
        assert r.url.path == "/api/tts_proxy/abc.mp3"
        return httpx.Response(200, content=b"mp3", headers={"content-type": "audio/mpeg"})

    ha = HomeAssistant("http://ha", "t")
    ha._client = httpx.AsyncClient(base_url="http://ha/api", transport=httpx.MockTransport(handler))
    assert await ha.tts("tts.piper", "ciao") == (b"mp3", "audio/mpeg")
    await ha.close()


def test_elevenlabs_reasons():
    import httpx

    from hubnex.integrations.elevenlabs import _reason

    def r(code, detail):
        return httpx.Response(code, json={"detail": detail})

    quota = {"status": "quota_exceeded", "message": "This request exceeds your quota of 10000. You have 523 credits remaining"}
    assert "ElevenLabs credits used up" in _reason(r(401, quota))
    assert "invalid API key" in _reason(r(401, {"status": "invalid_api_key", "message": "Invalid API key"}))
    assert "voice not found" in _reason(r(404, {"status": "voice_not_found", "message": "x"}))


def test_voice_text_is_made_for_the_ear():
    from hubnex.speech import for_voice

    said = for_voice(
        "Signore, ecco (CEI 64-8):\n\n• **Isolamento IT-M**: annuale\n- Nodo-PE: non oltre 0,2 Ω\n"
        "- 1,84 kW, oggi 9,6 kWh → F3 · 21,8°C\n1. Impianti MT/BT e/o UPS ≥ 10 kVA, 16 A\n"
        "Vedi DM 1/9/2021 e [la guida](https://x.it) ✅"
    )
    assert "0,2 ohms" in said and "1,84 kilowatts" in said and "21,8 degrees" in said
    assert "10 kilovolt amperes" in said and "1 September 2021" in said
    assert for_voice("Ciao. " * 100, limit=50) == "Ciao. " * 7 + "Ciao."
    assert for_voice("Accendo alle 7:30, 3 volte su 5") == "Accendo alle 7:30, 3 volte su 5."


def test_home_assistant_voice_by_name(settings, make_hq):
    settings.voice_tts_entity = "tts.home_assistant_cloud"
    settings.voice_tts_voice = "rinaldo"
    hq = make_hq([])
    asked, calls = [], []

    async def command(payload, timeout=30):
        calls.append(payload["type"])
        return {
            "get_config": {"language": "it"},
            "tts/engine/get": {"provider": {"engine_id": "x", "supported_languages": ["en-US", "it-IT"]}},
            "tts/engine/voices": {"voices": [{"voice_id": "DiegoNeural", "name": "Diego"},
                                             {"voice_id": "RinaldoNeural", "name": "Rinaldo"}]},
        }[payload["type"]]

    hq.watcher._command = command

    class FakeHA:
        enabled = True

        async def tts(self, engine, text, language=None, options=None):
            asked.append((engine, text, language, options))
            return b"mp3", "audio/mpeg"

        async def close(self):
            pass

    hq.ha = FakeHA()
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        assert client.post("/api/tts", json={"text": "Sono le 21,8°"}).status_code == 200
        assert client.post("/api/tts", json={"text": "Ancora"}).status_code == 200
        assert asked[0] == ("tts.home_assistant_cloud", "Sono le 21,8 degrees.", "en-US", {"voice": "RinaldoNeural"})
        assert calls.count("tts/engine/voices") == 1  # looked up once
        settings.voice_tts_voice = "Gandalf"
        r = client.post("/api/tts", json={"text": "Ciao"})
        assert r.status_code == 502 and "Available: Diego, Rinaldo" in r.json()["detail"]
