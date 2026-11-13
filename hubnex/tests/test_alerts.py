from datetime import datetime, timedelta, timezone

import pytest

from hubnex.alerts import clean_config, in_window
from tests.conftest import FakeTeam

T0 = datetime(2026, 11, 10, 18, 0)


def st(state, dc=None, name=None, changed=None, **attrs):
    a = dict(attrs)
    if dc:
        a["device_class"] = dc
    if name:
        a["friendly_name"] = name
    return {"state": state, "attributes": a, "last_changed": (changed or datetime.now(timezone.utc)).isoformat()}


@pytest.fixture
def house(make_hq):
    team = FakeTeam()
    hq = make_hq([], team=team)
    hq.watcher.states = {
        "binary_sensor.finestra_cucina": st("off", "window", "Finestra cucina"),
        "climate.soggiorno": st("heat", hvac_action="idle"),
        "person.anna": st("home"),
        "lock.ingresso": st("locked", name="Porta d'ingresso"),
        "binary_sensor.perdita_lavatrice": st("off", "moisture", "Lavatrice"),
        "light.soffitto": st("off", name="Soffitto"),
        "sensor.termostato_batteria": st("80", "battery", "Termostato", unit_of_measurement="%"),
    }
    hq.watcher.ready.set()
    calls = []

    async def call_service(domain, service, data=None, by_owner=False):
        calls.append((domain, service, data, by_owner))
        return []

    hq.ha.call_service = call_service
    hq.alerts.phones = [{"service": "mobile_app_pixel", "name": "Pixel"}]
    clock = {"now": T0}
    hq.now = lambda: clock["now"].replace(tzinfo=hq.tz)

    def at(minutes):
        clock["now"] = T0 + timedelta(minutes=minutes)

    return hq, team, calls, at


def pushes(calls, kind=None):
    out = [c for c in calls if c[0] == "notify" and c[1] == "mobile_app_pixel"]
    return [c for c in out if (c[2]["message"] == "clear_notification") == (kind == "clear")]


async def test_window_open_with_heating_waits_then_warns_then_clears(house):
    hq, team, calls, at = house
    hq.watcher.states["binary_sensor.finestra_cucina"]["state"] = "on"
    await hq.alerts.tick()
    assert not calls  # heating idle: nothing wrong
    hq.watcher.states["climate.soggiorno"]["attributes"]["hvac_action"] = "heating"
    await hq.alerts.tick()
    at(3)
    await hq.alerts.tick()
    assert not pushes(calls), "waits the 5 minutes"
    at(6)
    await hq.alerts.tick()
    [push] = pushes(calls)
    assert push[2]["title"] == "Windows open"
    assert "Finestra cucina" in push[2]["message"] and "heating" in push[2]["message"]
    assert push[2]["data"]["tag"] == "hubnex_windows"
    assert len(team.posts) == 1
    at(7)
    await hq.alerts.tick()
    assert len(pushes(calls)) == 1, "once per episode"
    hq.watcher.states["binary_sensor.finestra_cucina"]["state"] = "off"
    await hq.alerts.tick()
    [clear] = pushes(calls, "clear")
    assert clear[2]["data"]["tag"] == "hubnex_windows"
    # back within 30 minutes: no new warning (a window opened and closed again)
    hq.watcher.states["binary_sensor.finestra_cucina"]["state"] = "on"
    at(20)
    await hq.alerts.tick()
    at(30)
    await hq.alerts.tick()
    assert len(pushes(calls)) == 1


async def test_leak_warns_at_once_even_in_quiet_hours(house):
    hq, team, calls, at = house
    await hq.alerts.save({"quiet": {"from": "17:00", "to": "07:00"}})
    hq.watcher.states["binary_sensor.perdita_lavatrice"]["state"] = "on"
    await hq.alerts.tick()
    [push] = pushes(calls)
    assert "Water leak" in push[2]["title"] and "Lavatrice" in push[2]["message"]
    assert push[2]["data"]["priority"] == "high"
    assert any(c[:2] == ("persistent_notification", "create") for c in calls)


async def test_quiet_hours_hold_the_rest_until_they_end(house):
    hq, team, calls, at = house
    await hq.alerts.save({"quiet": {"from": "17:00", "to": "19:00"}})
    hq.watcher.states["sensor.termostato_batteria"]["state"] = "9"
    await hq.alerts.tick()
    at(40)
    await hq.alerts.tick()
    assert not pushes(calls)
    at(61)
    await hq.alerts.tick()
    [push] = pushes(calls)
    assert "Termostato 9%" in push[2]["message"]


async def test_nobody_home_lock_open_and_the_close_button(house):
    hq, team, calls, at = house
    hq.watcher.states["person.anna"]["state"] = "not_home"
    hq.watcher.states["lock.ingresso"]["state"] = "unlocked"
    await hq.alerts.tick()
    at(6)
    await hq.alerts.tick()
    [push] = pushes(calls)
    [button] = push[2]["data"]["actions"]
    assert button["title"] == "Close" and button["action"].startswith("HUBNEX_")
    assert team.posts[-1]["buttons"][0][0][1].startswith("h:")
    # pressed on the phone: Home Assistant sends the event, HubNEX locks
    await hq._ha_event("app_action", button["action"], {"action": button["action"]})
    assert ("lock", "lock", {"entity_id": "lock.ingresso"}, True) in calls
    # a second press does nothing
    n = len(calls)
    await hq._ha_event("app_action", button["action"], {"action": button["action"]})
    assert len(calls) == n


async def test_lights_at_night_offer_to_turn_them_off(house):
    hq, team, calls, at = house
    hq.watcher.states["light.soffitto"]["state"] = "on"
    at(60 * 6)  # 00:00
    await hq.alerts.tick()
    at(60 * 6 + 16)
    await hq.alerts.tick()
    [push] = pushes(calls)
    assert "Soffitto" in push[2]["message"]
    tok = push[2]["data"]["actions"][0]["action"][7:]
    await hq.alerts.press(tok)
    assert ("light", "turn_off", {"entity_id": ["light.soffitto"]}, True) in calls


async def test_offline_devices_use_home_assistants_clock(house):
    hq, team, calls, at = house
    now = hq.now()
    hq.watcher.states["light.soffitto"] = st("unavailable", name="Soffitto", changed=now - timedelta(hours=3))
    hq.watcher.states["light.nuova"] = st("unavailable", name="Nuova", changed=now - timedelta(minutes=2))  # not yet
    await hq.alerts.tick()
    [push] = pushes(calls)
    assert "Soffitto" in push[2]["message"] and "Nuova" not in push[2]["message"]


async def test_power_above_the_threshold(house):
    hq, team, calls, at = house
    hq.watcher.states["sensor.potenza"] = st("3.4", "power", "Potenza", unit_of_measurement="kW")
    hq.casa.adjust["energy"] = {"power": "sensor.potenza"}
    await hq.alerts.tick()
    at(11)
    await hq.alerts.tick()
    [push] = pushes(calls)
    assert "3.4 kW" in push[2]["message"]


async def test_excluded_entities_and_switched_off_rules(house):
    hq, team, calls, at = house
    await hq.alerts.save({"exclude": ["binary_sensor.perdita_lavatrice"], "rules": {"battery": {"on": False}}})
    hq.watcher.states["binary_sensor.perdita_lavatrice"]["state"] = "on"
    hq.watcher.states["sensor.termostato_batteria"]["state"] = "5"
    at(60)
    await hq.alerts.tick()
    assert not pushes(calls)


def test_config_is_cleaned():
    c = clean_config({"quiet": {"from": "25:00", "to": "07:00"}, "phones": ["mobile_app_x", "notify.evil"],
                      "rules": {"power": {"watts": "50", "minutes": "abc", "app": 0}}})
    assert c["quiet"] == {"from": "", "to": "07:00"}
    assert c["phones"] == ["mobile_app_x"]
    assert c["rules"]["power"]["watts"] == 100 and c["rules"]["power"]["minutes"] == 10
    assert c["rules"]["power"]["app"] is False
    assert clean_config(None)["phones"] is None


def test_time_windows_across_midnight():
    assert in_window(datetime(2026, 1, 1, 23, 45), "23:30", "06:00")
    assert in_window(datetime(2026, 1, 1, 2, 0), "23:30", "06:00")
    assert not in_window(datetime(2026, 1, 1, 12, 0), "23:30", "06:00")
    assert not in_window(datetime(2026, 1, 1, 12, 0), "", "")


async def test_people_unknown_while_home_assistant_restarts_is_not_away(house):
    hq, team, calls, at = house
    hq.watcher.states["person.anna"]["state"] = "unknown"
    hq.watcher.states["lock.ingresso"]["state"] = "unlocked"
    await hq.alerts.tick()
    at(10)
    await hq.alerts.tick()
    assert not pushes(calls)


async def test_battery_says_which_device_and_where(house):
    hq, team, calls, at = house
    hq.watcher.states["sensor.batteria_5"] = st("8", "battery", "Batteria", unit_of_measurement="%")
    hq.watcher.entities["sensor.batteria_5"] = {"entity_id": "sensor.batteria_5", "device_id": "d1"}
    hq.watcher.devices["d1"] = {"id": "d1", "name": "Sensore porta", "area_id": "ingresso"}
    hq.watcher.areas["ingresso"] = {"area_id": "ingresso", "name": "Ingresso"}
    await hq.alerts.tick()
    at(31)
    await hq.alerts.tick()
    [push] = pushes(calls)
    assert "Sensore porta (Ingresso) 8%" in push[2]["message"]


async def test_no_emoji_in_the_messages(house):
    hq, team, calls, at = house
    hq.watcher.states["binary_sensor.perdita_lavatrice"]["state"] = "on"
    await hq.alerts.tick()
    texts = [team.posts[-1]["text"]] + [c[2]["title"] + c[2]["message"] for c in pushes(calls)]
    assert team.posts[-1]["text"].startswith("URGENT: Water leak")
    assert all(ch.isascii() or ch.isalpha() or ch in "àèéìòù'’ " for t in texts for ch in t)


async def test_pellet_below_the_threshold_asks_to_reorder_once(house):
    hq, team, calls, at = house
    hq.watcher.states["counter.carico_pellet"] = st("6", name="Carico pellet")  # a counter, by name a stock
    assert hq.casa.stocks() == ["counter.carico_pellet"]
    await hq.alerts.tick()
    assert pushes(calls) == []  # 6 > 5
    hq.watcher.states["counter.carico_pellet"] = st("5", name="Carico pellet")
    await hq.alerts.tick()
    [push] = pushes(calls)
    assert "Carico pellet: 5 left, below the threshold of 5" in push[2]["message"]
    hq.watcher.states["counter.carico_pellet"] = st("4", name="Carico pellet")
    at(30)
    await hq.alerts.tick()
    assert len(pushes(calls)) == 1  # one warning per episode
    hq.watcher.states["counter.carico_pellet"] = st("19", name="Carico pellet")  # the delivery came
    at(60)
    await hq.alerts.tick()
    assert len(pushes(calls, "clear")) == 1
    await hq.casa.set_stock("counter.carico_pellet", 15, 20)  # the owner's own threshold
    assert hq.casa.stock_of("counter.carico_pellet") == {"delivery": 15, "low": 20}
