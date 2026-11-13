"""The add-on configuration page: every option is read, translated, and reaches the settings."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from hubnex import config as cfg
from hubnex.config import ADDON_OPTIONS, ConnectorSpec, Settings
from hubnex.connectors import Connectors

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def from_options(monkeypatch, tmp_path, options: dict) -> Settings:
    for env in ADDON_OPTIONS.values():
        monkeypatch.setenv(env, "")  # restored after the test
    path = tmp_path / "options.json"
    path.write_text(json.dumps(options))
    assert cfg._load_addon_options(str(path), str(tmp_path / "missing"))
    monkeypatch.setattr(cfg, "_load_addon_options", lambda: True)
    return Settings.from_env()


def test_every_option_has_a_schema_a_setting_and_its_words():
    options, schema = set(MANIFEST["options"]), set(MANIFEST["schema"])
    assert options == schema
    assert options - set(ADDON_OPTIONS) == set()
    for lang in ("en", "nl", "it"):
        words = yaml.safe_load((ROOT / "translations" / f"{lang}.yaml").read_text(encoding="utf-8"))["configuration"]
        assert sorted(schema - set(words)) == [], lang
        assert all(words[k].get("name") for k in schema), lang


def test_the_page_defaults_keep_todays_behaviour(monkeypatch, tmp_path):
    s = from_options(monkeypatch, tmp_path, MANIFEST["options"])
    d = Settings()
    for field in ("chat_history_turns", "chat_voice_history_turns", "chat_new_session_after_hours",
                  "chat_keep_sessions", "chat_trash_days", "chat_live_text", "chat_show_tools", "chat_max_parallel",
                  "ha_mcp_enabled", "ha_mcp_groups", "ha_mcp_confirm", "ha_mcp_free_tools", "ha_voice_blocked_services",
                  "ha_voice_exposed_only", "ha_action_log_days", "mcp_expose", "mcp_expose_tools",
                  "mcp_expose_read_only", "mcp_connectors", "mcp_use_server_instructions", "mcp_image_results",
                  "mcp_tool_search", "mcp_max_result_kb"):
        assert getattr(s, field) == getattr(d, field), field
    assert s.ha_mcp_agents is None and s.ha_protected_entities == ()


def test_page_values_reach_the_settings(monkeypatch, tmp_path):
    s = from_options(monkeypatch, tmp_path, {
        "chat_history_turns": 40, "chat_new_session_after_hours": 6, "chat_live_text": False,
        "chat_max_parallel": 99,  # beyond the schema: clamped
        "ha_mcp_groups": ["read", "dashboards", "nonsense"], "ha_mcp_exclude_tools": "render_template, fire_event",
        "ha_mcp_agents": "boss,technical", "ha_mcp_confirm": "always", "ha_mcp_free_tools": "",
        "ha_protected_entities": "Lock.Front_Door,alarm_control_panel.*",
        "mcp_expose": True, "mcp_expose_tools": ["ha", "sessions"], "mcp_token": "t0k",
        "mcp_connectors": [{"name": "Gestionale", "url": "https://x/mcp", "agents": "technical", "free": "a, b"}],
        "mcp_tool_search": True, "mcp_max_result_kb": 50,
    })
    assert s.chat_history_turns == 40 and s.chat_new_session_after_hours == 6 and s.chat_live_text is False
    assert s.chat_max_parallel == 8
    assert s.ha_mcp_groups == ("read", "dashboards")
    assert s.ha_mcp_exclude_tools == {"render_template", "fire_event"}
    assert s.ha_mcp_agents == ["boss", "technical"] and s.ha_mcp_confirm == "always"
    assert s.ha_mcp_free_tools == set(cfg._csv(cfg.DEFAULT_HA_MCP_FREE))  # empty on the page: the default
    assert s.ha_protected_entities == ("lock.front_door", "alarm_control_panel.*")
    assert s.mcp_expose and s.mcp_expose_tools == ("ha", "sessions") and s.mcp_token == "t0k"
    assert s.mcp_connectors == [{"name": "Gestionale", "url": "https://x/mcp", "agents": "technical", "free": "a, b"}]
    assert s.mcp_tool_search and s.mcp_max_result_kb == 50


def test_page_connectors_join_and_win_over_agents_yaml(make_hq):
    hq = make_hq([])
    hq.settings.mcp_connectors = [
        {"name": "Gestionale", "url": "https://page/mcp", "agents": "technical", "free": "crea_bozza", "exclude": "x"},
        {"name": "Agenda", "url": "https://agenda/mcp"},
        {"name": "", "url": "https://broken"},  # skipped
    ]
    yaml_spec = ConnectorSpec(name="Gestionale", url="https://yaml/mcp")
    c = Connectors(hq, [yaml_spec])
    assert set(c.items) == {"gestionale", "agenda"}
    g = c.items["gestionale"].spec
    assert g.url == "https://page/mcp" and g.agents == ["technical"] and g.free == ["crea_bozza"] and g.exclude == ["x"]
    assert c.items["agenda"].spec.agents is None
