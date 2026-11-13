from datetime import datetime
from types import SimpleNamespace as NS

from hubnex.pricing import call_cost
from tests.conftest import FakeTeam, response, text_block


def usage(i=1000, o=100):
    return NS(input_tokens=i, output_tokens=o, cache_read_input_tokens=0, cache_creation_input_tokens=0)


def at(hq, when: datetime):
    hq.now = lambda: when.replace(tzinfo=hq.tz)


async def test_spend_is_booked_per_day_agent_and_model(make_hq):
    hq = make_hq([])
    at(hq, datetime(2026, 11, 10, 12, 0))
    await hq.on_usage(usage(), "claude-sonnet-5-5", "jarvis")
    await hq.on_usage(usage(), "claude-sonnet-5-5", "jarvis")
    await hq.on_usage(usage(), "claude-haiku-5-5", "mail")
    at(hq, datetime(2026, 11, 9, 20, 0))
    await hq.on_usage(usage(), "claude-haiku-5-5", "plan")

    at(hq, datetime(2026, 11, 10, 12, 0))
    c = await hq.costs(7)
    sonnet, haiku = call_cost("claude-sonnet-5-5", usage()), call_cost("claude-haiku-5-5", usage())
    assert [d["day"] for d in c["days"]][-2:] == ["2026-11-09", "2026-11-10"]
    assert c["days"][0]["day"] == "2026-11-04" and c["days"][0]["cost"] == 0
    assert c["today"] == round(2 * sonnet + haiku, 4)
    agents = {a["id"]: a for a in c["by_agent"]}
    assert agents["jarvis"]["calls"] == 2 and agents["jarvis"]["tokens_in"] == 2000
    assert agents["plan"]["name"] == "Floor plan proposal"
    assert c["by_agent"][0]["id"] == "jarvis"  # most expensive first
    assert {m["id"] for m in c["by_model"]} == {"claude-sonnet-5-5", "claude-haiku-5-5"}
    assert abs(c["month"]["spent"] - (2 * sonnet + 2 * haiku)) < 1e-6


async def test_month_forecast_follows_the_pace(make_hq):
    hq = make_hq([])
    at(hq, datetime(2026, 11, 2, 0, 0))
    for _ in range(10):
        await hq.on_usage(usage(100_000, 10_000), "claude-sonnet-5-5", "jarvis")
    at(hq, datetime(2026, 11, 1, 10, 0))  # day one: too early to estimate
    assert (await hq.costs())["month"]["forecast"] is None
    at(hq, datetime(2026, 11, 3, 0, 0))  # two days gone in a 30-day month
    c = await hq.costs()
    assert abs(c["month"]["forecast"] - c["month"]["spent"] * 15) < 0.05


async def test_budget_warns_once_at_80_and_once_at_100(make_hq, settings):
    settings.monthly_budget_usd = 1.0
    team = FakeTeam()
    hq = make_hq([], team=team)
    calls = []

    async def fake_service(domain, service, data):
        calls.append(data["notification_id"])

    hq.ha.call_service = fake_service
    at(hq, datetime(2026, 11, 10, 12, 0))
    big = usage(300_000, 0)  # 0.60 $ with Sonnet
    await hq.on_usage(big, "claude-sonnet-5-5", "jarvis")
    assert not team.posts
    await hq.on_usage(usage(100_000, 0), "claude-sonnet-5-5", "jarvis")  # 0.80 $
    await hq.on_usage(usage(10, 0), "claude-sonnet-5-5", "jarvis")
    assert len(team.posts) == 1 and "80%" in team.posts[0]["text"]
    await hq.on_usage(usage(100_000, 0), "claude-sonnet-5-5", "jarvis")  # 1.00 $
    await hq.on_usage(usage(100_000, 0), "claude-sonnet-5-5", "jarvis")
    assert len(team.posts) == 2 and "exceeded" in team.posts[1]["text"]
    assert calls == ["hubnex_budget", "hubnex_budget"]
    at(hq, datetime(2026, 12, 1, 9, 0))  # a new month starts from zero
    await hq.on_usage(usage(10, 0), "claude-sonnet-5-5", "jarvis")
    assert len(team.posts) == 2


async def test_agent_calls_are_booked_to_that_agent(make_hq):
    hq = make_hq([response([text_block("Fatto.")], "end_turn")])
    await hq.run_agent("accountant", "controlla le scadenze", source="user")
    c = await hq.costs(1)
    assert [a["id"] for a in c["by_agent"]] == ["accountant"]
