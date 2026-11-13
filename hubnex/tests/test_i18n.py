"""Add-on messages and replies: English by default, Dutch when chosen."""

import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from hubnex import i18n
from hubnex.main import create_app
from hubnex.speech import for_voice
from tests.conftest import ROOT, response, text_block


def test_every_message_has_its_english():
    out = subprocess.run([sys.executable, "dev/i18n_keys.py", "--python", "--missing"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [], "messages without English: add them to hubnex/i18n_en.py"


@pytest.fixture
def dutch():
    i18n.set_system_lang("nl")
    yield
    i18n.set_system_lang("en")


def test_every_message_has_its_dutch():
    out = subprocess.run([sys.executable, "dev/i18n_keys.py", "--python", "--missing", "--lang", "nl"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [], "messages without Dutch: add them to hubnex/i18n_nl.py"


def test_dutch_follows_the_request_then_the_add_on():
    token = i18n.REQUEST_LANG.set(i18n.norm("nl-BE"))
    try:
        assert i18n.tr("bozza sconosciuta") == "onbekend concept"
        assert i18n.tr("inviata alle {time}", time="10:00") == "verstuurd om 10:00"
        assert i18n.tr_sys("bozza sconosciuta") == "unknown draft"  # the add-on itself is in English
    finally:
        i18n.REQUEST_LANG.reset(token)
    assert i18n.norm("nl-NL") == "nl"


def test_the_add_on_can_speak_dutch(dutch):
    assert i18n.tr_sys("bozza sconosciuta") == "onbekend concept"
    assert i18n.tr("{n} stanze", n=3) == "3 kamers"


async def test_jarvis_answers_in_dutch(make_hq, dutch):
    hq = make_hq([response([text_block("Klaar.")], "end_turn")])
    i18n.set_system_lang("nl")  # the HQ took the add-on's option (en) when it was made
    await hq.chat("t", "doe het licht in de keuken aan")
    system = hq.client.requests[-1]["system"]
    assert "Always reply in Dutch" in system and "Always reply in English" not in system


def test_api_errors_in_the_viewers_language(settings, make_hq):
    with TestClient(create_app(settings, hq=make_hq([]), start_workers=False)) as client:
        r = client.get("/api/agents/nobody", headers={"X-HubNEX-Lang": "nl"})
        assert r.json()["detail"] == "onbekende agent"


def test_the_voice_reads_dutch():
    said = for_voice("Vermogen 1,84 kW, vandaag 9,6 kWh, 21,5°C, bijv. op 1/9/2026 ✅", lang="nl")
    assert said == "Vermogen 1,84 kilowatt, vandaag 9,6 kilowattuur, 21,5 graden, bijvoorbeeld op 1 september 2026."


def test_language_option(monkeypatch):
    from hubnex.config import Settings
    for value, expected in (("nl", "nl"), ("auto", "auto"), ("", "en"), ("fr", "en")):
        monkeypatch.setenv("HUBNEX_LANGUAGE", value)
        assert Settings.from_env().language == expected


def test_messages_are_english_even_for_italian_requests():
    assert i18n.tr("bozza sconosciuta") == "unknown draft"
    token = i18n.REQUEST_LANG.set(i18n.norm("it-IT"))
    try:
        assert i18n.tr("bozza sconosciuta") == "unknown draft"
        assert i18n.tr("inviata alle {time}", time="10:00") == "sent at 10:00"
        assert i18n.tr_sys("bozza sconosciuta") == "unknown draft"
    finally:
        i18n.REQUEST_LANG.reset(token)
    assert i18n.norm("en-GB") == i18n.norm("it-IT") == i18n.norm("de") == "en"


async def test_jarvis_answers_in_english(make_hq):
    hq = make_hq([response([text_block("Done, Sir.")], "end_turn")])
    await hq.chat("t", "turn on the kitchen light")
    system = hq.client.requests[-1]["system"]
    assert "Always reply in English" in system
    assert hq.agent_system(hq.org.agents[0]).count("Always reply in English") == 1


def test_api_errors_are_english(settings, make_hq):
    with TestClient(create_app(settings, hq=make_hq([]), start_workers=False)) as client:
        assert client.get("/api/agents/nobody").json()["detail"] == "unknown agent"
        r = client.get("/api/agents/nobody", headers={"X-HubNEX-Lang": "it-IT"})
        assert r.json()["detail"] == "unknown agent"


def test_the_voice_reads_english():
    said = for_voice("Power 1.84 kW, today 9.6 kWh, 21.5°C, e.g. a UPS ≥ 10 kVA on 1/9/2026 ✅")
    assert said == ("Power 1.84 kilowatts, today 9.6 kilowatt hours, 21.5 degrees, for example a UPS "
                    "at least 10 kilovolt amperes on 1 September 2026.")
    assert for_voice("0,2 Ω", lang="it") == "0,2 ohm."


def test_energy_bands_default_to_single():
    from hubnex.energy import clean_config
    assert clean_config({})["band_mode"] == "single"
    assert clean_config({"band_mode": "arera"})["band_mode"] == "arera"  # chosen on purpose
    i18n.set_system_lang("it")
    assert clean_config({})["band_mode"] == "single"


def test_english_example_team(tmp_path, monkeypatch):
    from hubnex import config
    from hubnex.config import load_org
    org = load_org(str(config.DEFAULT_AGENTS_EN))
    assert org.boss_name == "Jarvis" and {c.name for c in org.companies} == {"Work", "Home"}
    assert "accountant" in {a.id for a in org.agents}
    # First start of the add-on uses the English example, regardless of Home Assistant's language.
    opts, cfg = tmp_path / "options.json", tmp_path / "cfg"
    opts.write_text("{}")
    cfg.mkdir()
    monkeypatch.setenv("HUBNEX_LANGUAGE", "it")
    import os
    saved = dict(os.environ)
    for k in ("HUBNEX_AGENTS_FILE", "HUBNEX_CASA_FILE", "HUBNEX_DB", "HUBNEX_INTERNAL_TOKEN"):
        os.environ.pop(k, None)
    try:
        assert config._load_addon_options(str(opts), str(cfg))
        assert "Jarvis Butler" in (cfg / "agents.yaml").read_text()
    finally:  # the add-on sets its environment: give the other tests theirs back
        os.environ.clear()
        os.environ.update(saved)
