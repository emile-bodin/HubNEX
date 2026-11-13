"""Read-only look at the past of the house: Home Assistant history, logbook and statistics.

Everything here only reads (recorder history and logbook over REST, long-term statistics over
the WebSocket already open for the house view) and keeps the answers small enough for the
model: unavailable/unknown dropped, repeated states collapsed, at most 14 days and 25 entities
per call, and a clear note when something had to be cut.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
from statistics import median_low
from zoneinfo import ZoneInfo

from hubnex.tools import ToolContext, tool
from hubnex.tools.homeassistant import _ha

MAX_DAYS = 14
MAX_ENTITIES = 25
MAX_SUMMARY_ENTITIES = 60
MAX_STATISTIC_IDS = 10
MAX_CHARS = 12_000
SKIP = {"unavailable", "unknown", "", None}
# States that count as "on" for the typical on/off times of the summary.
ACTIVE = {
    "on", "open", "opening", "home", "playing", "unlocked", "unlocking", "heat", "cool", "heat_cool",
    "heating", "cooling", "drying", "fan_only", "cleaning", "returning", "detected", "triggered", "pending",
}
NARROW = "narrow the time range or the entities, or use ha_summarize_history"
STAT_PERIODS = {"hour": (1, MAX_DAYS), "day": (30, 366), "week": (182, 366), "month": (366, 366)}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
RELATIVE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(m|min|h|d|w)\s*$", re.I)
UNITS = {"m": "minutes", "min": "minutes", "h": "hours", "d": "days", "w": "weeks"}

TIME_HELP = "ISO time (2026-11-12T08:00, local time if no offset), a date (2026-11-12) or relative ('24h', '3d', '1w')"


# ---------------------------------------------------------------------- time
def _local_tz(ctx: ToolContext):
    """Home Assistant's time zone, else the system's."""
    name = getattr(getattr(ctx.hq, "watcher", None), "time_zone", None)
    if name:
        try:
            return ZoneInfo(name)
        except Exception:  # unknown name or no tz database
            pass
    return datetime.now().astimezone().tzinfo


def _parse_time(text, tz, now: datetime) -> datetime | None:
    if text in (None, ""):
        return None
    text = str(text).strip()
    if text.lower() == "now":
        return now
    m = RELATIVE.match(text)
    if m:
        return now - timedelta(**{UNITS[m.group(2).lower()]: float(m.group(1))})
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"could not read the time '{text}': use {TIME_HELP}") from None
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt


def _window(inp: dict, tz, max_days: int = MAX_DAYS, default: timedelta = timedelta(hours=24)):
    """(start, end, notes): end defaults to now, start to `default` before end."""
    now = datetime.now(tz)
    end = min(_parse_time(inp.get("end"), tz, now) or now, now)
    start = _parse_time(inp.get("start"), tz, now) or end - default
    if start >= end:
        raise ValueError("start must be before end (and in the past)")
    notes = []
    if end - start > timedelta(days=max_days):
        start = end - timedelta(days=max_days)
        notes.append(f"range limited to {max_days} days: shown from {_fmt(start, tz)}")
    return start, end, notes


def _to_dt(ts) -> datetime | None:
    if ts in (None, ""):
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts, timezone.utc)  # statistics use ms
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fmt(ts, tz, day: bool = False) -> str:
    dt = ts if isinstance(ts, datetime) else _to_dt(ts)
    if dt is None:
        return str(ts or "")
    return dt.astimezone(tz).strftime("%Y-%m-%d" if day else "%Y-%m-%d %H:%M")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------- entities
async def _known(ctx: ToolContext) -> list[str]:
    w = getattr(ctx.hq, "watcher", None)
    if w is not None and w.ready.is_set() and w.states:
        return list(w.states)
    return [e["entity_id"] for e in await _ha(ctx).list_entities()]


async def _resolve(ctx: ToolContext, raw, limit: int) -> tuple[list[str], list[str], list[str]]:
    """Comma-separated ids, 'domain.*' wildcards or a bare domain -> (ids, unknown, notes)."""
    tokens = [t.strip().lower() for t in str(raw or "").split(",") if t.strip()]
    if not tokens:
        raise ValueError("give at least one entity_id (or a wildcard like 'binary_sensor.*')")
    known = await _known(ctx)
    known_set = set(known)
    ids, unknown, notes = [], [], []
    for t in tokens:
        pattern = t if "." in t else f"{t}.*"  # "light" = every light
        if "*" in pattern or "?" in pattern:
            hits = sorted(e for e in known if fnmatchcase(e, pattern))
            if not hits:
                notes.append(f"nothing matches '{t}'")
            ids.extend(hits)
        elif t in known_set:
            ids.append(t)
        else:
            unknown.append(t)
    ids = list(dict.fromkeys(ids))
    if not ids:
        what = ", ".join(unknown) if unknown else ", ".join(tokens)
        raise LookupError(f"unknown entity: {what}. Check the entity_id with ha_list_entities.")
    if len(ids) > limit:
        notes.append(f"{len(ids)} entities match: only the first {limit} are included; {NARROW}")
        ids = ids[:limit]
    return ids, unknown, notes


# ---------------------------------------------------------------------- shaping
def _compact(series: list[dict], tz, attrs: list[str] | None = None) -> list[list]:
    """[[local time, state(, {attributes})], ...] without unavailable/unknown and repeats."""
    out, last = [], None
    for p in series:
        state = p.get("state")
        if state in SKIP:
            continue
        extra = {}
        if attrs:
            have = p.get("attributes") or {}
            extra = {k: have[k] for k in attrs if k in have}
        key = (state, json.dumps(extra, sort_keys=True, default=str))
        if key == last:
            continue
        last = key
        row = [_fmt(p.get("last_changed") or p.get("last_updated"), tz), state]
        if attrs:
            row.append(extra)
        out.append(row)
    return out


def _fit(result: dict, lists: list[list]) -> int:
    """Drop the oldest rows of the longest lists until the result fits; how many were dropped."""
    dropped = 0
    while len(json.dumps(result, ensure_ascii=False, default=str)) > MAX_CHARS:
        longest = max(lists, key=len, default=[])
        if len(longest) <= 1:
            break
        n = max(1, len(longest) // 5)
        del longest[:n]
        dropped += n
    return dropped


def _finish(out: dict, notes: list[str], unknown: list[str]) -> dict:
    if unknown:
        out["unknown"] = unknown
    if notes:
        out["notes"] = notes
    return out


def _series_by_entity(rows) -> dict[str, list[dict]]:
    out = {}
    for series in rows or []:
        if series and series[0].get("entity_id"):
            out[series[0]["entity_id"]] = series
    return out


# ---------------------------------------------------------------------- tools
@tool(
    "ha_get_history",
    "Read-only: how the state of Home Assistant entities changed in the past (any domain: person, "
    "device_tracker, binary_sensor, sensor, climate, light, switch, cover, lock, alarm, media_player, "
    "vacuum, weather…). Returns [local time, state] per change, repeats and unavailable left out. "
    f"Default: the last 24 hours; at most {MAX_DAYS} days and {MAX_ENTITIES} entities per call. For "
    "habits over several days use ha_summarize_history; for long periods of numeric sensors "
    "ha_get_statistics.",
    {
        "entity_id": {"type": "string", "description": "One or more comma-separated entity_ids, or a wildcard like 'binary_sensor.*'"},
        "start": {"type": "string", "description": f"From: {TIME_HELP}. Default 24h ago"},
        "end": {"type": "string", "description": "Until (same formats). Default now"},
        "include_attributes": {"type": "array", "items": {"type": "string"},
                               "description": "Attributes to include, e.g. ['temperature', 'hvac_action']. Default none"},
    },
    ["entity_id"],
)
async def ha_get_history(ctx: ToolContext, inp: dict):
    ha = _ha(ctx)
    tz = _local_tz(ctx)
    start, end, notes = _window(inp, tz)
    ids, unknown, more = await _resolve(ctx, inp.get("entity_id"), MAX_ENTITIES)
    notes += more
    attrs = [str(a) for a in inp.get("include_attributes") or [] if str(a).strip()]
    rows = await ha.history_period(ids, _iso(start), _iso(end), attributes=bool(attrs))
    entities = {}
    for eid, series in _series_by_entity(rows).items():
        points = _compact(series, tz, attrs)
        if points:
            entities[eid] = points
    if not entities:
        msg = (f"No state changes for {', '.join(ids)} between {_fmt(start, tz)} and {_fmt(end, tz)} "
               "(is the recorder keeping these entities?)")
        return " ".join([msg, *notes] + ([f"Unknown: {', '.join(unknown)}."] if unknown else []))
    out = {"from": _fmt(start, tz), "to": _fmt(end, tz), "time_zone": str(tz), "entities": entities}
    missing = [e for e in ids if e not in entities]
    if missing:
        out["no_data"] = missing
    dropped = _fit(out, list(entities.values()))
    if dropped:
        notes.append(f"output too long: the oldest {dropped} changes were left out; {NARROW}")
    return _finish(out, notes, unknown)


@tool(
    "ha_get_logbook",
    "Read-only: Home Assistant's logbook, readable events (\"Front door opened\", \"Alarm armed\", "
    "\"Anna arrived home\") for the whole house or for some entities. Default: the last 24 hours; "
    f"at most {MAX_DAYS} days.",
    {
        "entity_id": {"type": "string", "description": "Optional: entity_id(s), comma-separated, or a wildcard. Empty = whole house"},
        "start": {"type": "string", "description": f"From: {TIME_HELP}. Default 24h ago"},
        "end": {"type": "string", "description": "Until (same formats). Default now"},
    },
)
async def ha_get_logbook(ctx: ToolContext, inp: dict):
    ha = _ha(ctx)
    tz = _local_tz(ctx)
    start, end, notes = _window(inp, tz)
    ids, unknown = [], []
    if str(inp.get("entity_id") or "").strip():
        ids, unknown, more = await _resolve(ctx, inp["entity_id"], MAX_ENTITIES)
        notes += more
    raw = await ha.logbook(_iso(start), _iso(end), ",".join(ids) or None)
    entries, last = [], None
    for e in raw or []:
        message = (e.get("message") or "").strip()
        if e.get("state") in ("unavailable", "unknown") or message in ("became unavailable", "became unknown"):
            continue
        text = message or (f"changed to {e['state']}" if e.get("state") else "")
        key = (e.get("entity_id"), text)
        if key == last:
            continue
        last = key
        row = [_fmt(e.get("when"), tz), e.get("name") or e.get("entity_id") or "", text]
        if e.get("entity_id"):
            row.append(e["entity_id"])
        entries.append(row)
    if not entries:
        who = ", ".join(ids) if ids else "the house"
        return f"No logbook entries for {who} between {_fmt(start, tz)} and {_fmt(end, tz)}."
    out = {"from": _fmt(start, tz), "to": _fmt(end, tz), "time_zone": str(tz), "entries": entries}
    dropped = _fit(out, [entries])
    if dropped:
        notes.append(f"output too long: the oldest {dropped} entries were left out; {NARROW}")
    return _finish(out, notes, unknown)


@tool(
    "ha_get_statistics",
    "Read-only: long-term statistics of numeric sensors (energy, temperature, power, gas, water…) "
    "aggregated per hour, day, week or month: mean, min, max, and for meters sum/change. For long "
    "periods (hour: up to 14 days, day/week/month: up to a year). Only entities with a state_class "
    "have statistics.",
    {
        "statistic_id": {"type": "string", "description": f"One or more comma-separated ids (usually the entity_id), max {MAX_STATISTIC_IDS}"},
        "period": {"type": "string", "enum": list(STAT_PERIODS), "description": "Default 'hour'"},
        "start": {"type": "string", "description": f"From: {TIME_HELP}. Default: 24h (hour), 30 days (day)…"},
        "end": {"type": "string", "description": "Until (same formats). Default now"},
    },
    ["statistic_id"],
)
async def ha_get_statistics(ctx: ToolContext, inp: dict):
    _ha(ctx)
    w = getattr(ctx.hq, "watcher", None)
    if w is None or not w.enabled or not w.ready.is_set():
        raise RuntimeError("Home Assistant WebSocket not connected: statistics are not available now, try ha_get_history.")
    period = str(inp.get("period") or "hour").lower()
    if period not in STAT_PERIODS:
        raise ValueError(f"period must be one of: {', '.join(STAT_PERIODS)}")
    default_days, max_days = STAT_PERIODS[period]
    tz = _local_tz(ctx)
    start, end, notes = _window(inp, tz, max_days, timedelta(days=default_days))
    ids = list(dict.fromkeys(t.strip().lower() for t in str(inp.get("statistic_id") or "").split(",") if t.strip()))
    if not ids:
        raise ValueError("give at least one statistic_id")
    if len(ids) > MAX_STATISTIC_IDS:
        notes.append(f"only the first {MAX_STATISTIC_IDS} of {len(ids)} ids are included")
        ids = ids[:MAX_STATISTIC_IDS]
    try:
        raw = await w.statistics(ids, _iso(start), _iso(end), period)
    except asyncio.TimeoutError:
        raise RuntimeError("Home Assistant did not answer in time: try a shorter period") from None
    except Exception as exc:
        raise RuntimeError(f"statistics: {exc}") from None
    stats, lists = {}, []
    for sid in ids:
        rows = (raw or {}).get(sid) or []
        cols = [c for c in ("mean", "min", "max", "sum", "change") if any(r.get(c) is not None for r in rows)]
        if not rows or not cols:
            continue
        table = [[_fmt(r.get("start"), tz, day=period != "hour")]
                 + [round(r[c], 2) if isinstance(r.get(c), (int, float)) else r.get(c) for c in cols] for r in rows]
        stats[sid] = {"columns": ["time", *cols], "rows": table}
        lists.append(table)
    if not stats:
        return (f"No statistics for {', '.join(ids)} between {_fmt(start, tz)} and {_fmt(end, tz)}: only "
                "numeric sensors with a state_class have them (use ha_get_history for the others).")
    out = {"from": _fmt(start, tz), "to": _fmt(end, tz), "time_zone": str(tz), "period": period, "statistics": stats}
    missing = [s for s in ids if s not in stats]
    if missing:
        out["no_statistics"] = missing
    dropped = _fit(out, lists)
    if dropped:
        notes.append(f"output too long: the oldest {dropped} rows were left out; use a longer period or fewer ids")
    return _finish(out, notes, [])


def _summarize(series: list[dict], start: datetime, end: datetime, tz) -> dict | None:
    points = []
    for p in series:
        state = p.get("state")
        t = _to_dt(p.get("last_changed") or p.get("last_updated"))
        if t is None or t >= end:
            continue
        t = max(t, start)
        if points and points[-1][1] == state:
            continue
        points.append((t, state))
    if not points:
        return None
    total = (end - start).total_seconds()
    segments = [(t, s, ((points[i + 1][0] if i + 1 < len(points) else end) - t).total_seconds())
                for i, (t, s) in enumerate(points)]
    valid = [(t, s, d) for t, s, d in segments if s not in SKIP]
    if not valid:
        return None
    collapsed = []
    for t, s, _ in valid:
        if not collapsed or collapsed[-1][1] != s:
            collapsed.append((t, s))
    out = {"changes": len(collapsed) - 1, "last": collapsed[-1][1], "last_change": _fmt(collapsed[-1][0], tz)}
    try:
        values = [(float(s), d) for _, s, d in valid]
    except ValueError:
        values = None
    if values:
        weight = sum(d for _, d in values)
        out.update(min=min(v for v, _ in values), max=max(v for v, _ in values),
                   mean=round(sum(v * d for v, d in values) / weight, 2) if weight else values[-1][0])
        return out
    in_state: dict[str, float] = {}
    for _, s, d in valid:
        in_state[s] = in_state.get(s, 0) + d
    out["time_in_state"] = {
        s: {"hours": round(d / 3600, 1), "pct": round(100 * d / total, 1)}
        for s, d in sorted(in_state.items(), key=lambda kv: -kv[1])
    }
    if any(s in ACTIVE or s.startswith("armed") for s in in_state):
        out["typical"] = _typical(collapsed, tz)
    return out


def _typical(points: list[tuple[datetime, str]], tz) -> dict:
    """Per weekday: median time of the first switch to 'on' and the last switch to 'off'."""
    def active(s):
        return s in ACTIVE or s.startswith("armed")

    first_on: dict = {}
    last_off: dict = {}
    for (_, prev), (t, cur) in zip(points, points[1:]):
        local = t.astimezone(tz)
        day, minute = local.date(), local.hour * 60 + local.minute
        if active(cur) and not active(prev):
            first_on.setdefault(day, minute)
        elif active(prev) and not active(cur):
            last_off[day] = minute
    out = {}
    for i, name in enumerate(WEEKDAYS):
        ons = [m for d, m in first_on.items() if d.weekday() == i]
        offs = [m for d, m in last_off.items() if d.weekday() == i]
        if not ons and not offs:
            continue
        row = {"days": len({d for d in (*first_on, *last_off) if d.weekday() == i})}
        if ons:
            row["first_on"] = "%02d:%02d" % divmod(median_low(ons), 60)
        if offs:
            row["last_off"] = "%02d:%02d" % divmod(median_low(offs), 60)
        out[name] = row
    return out


@tool(
    "ha_summarize_history",
    "Read-only: a compact summary of the past of entities, to understand habits and routines without "
    "reading every change. Per entity: number of changes, time spent in each state (hours, %), for "
    "numeric sensors min/mean/max, and per weekday the typical first 'on' and last 'off' time (on = "
    f"on, open, home, playing, unlocked, heating, cleaning, armed…). Default: the last 7 days; at most "
    f"{MAX_DAYS} days and {MAX_SUMMARY_ENTITIES} entities.",
    {
        "entity_id": {"type": "string", "description": "entity_id(s), comma-separated, a wildcard ('binary_sensor.*') or a domain ('light')"},
        "start": {"type": "string", "description": f"From: {TIME_HELP}. Default 7 days ago"},
        "end": {"type": "string", "description": "Until (same formats). Default now"},
    },
    ["entity_id"],
)
async def ha_summarize_history(ctx: ToolContext, inp: dict):
    ha = _ha(ctx)
    tz = _local_tz(ctx)
    start, end, notes = _window(inp, tz, default=timedelta(days=7))
    ids, unknown, more = await _resolve(ctx, inp.get("entity_id"), MAX_SUMMARY_ENTITIES)
    notes += more
    rows = await ha.history_period(ids, _iso(start), _iso(end))
    summary = {}
    for eid, series in _series_by_entity(rows).items():
        s = _summarize(series, start, end, tz)
        if s:
            summary[eid] = s
    if not summary:
        return (f"No history for {', '.join(ids)} between {_fmt(start, tz)} and {_fmt(end, tz)} "
                "(is the recorder keeping these entities?)")
    out = {"from": _fmt(start, tz), "to": _fmt(end, tz), "time_zone": str(tz), "entities": summary}
    missing = [e for e in ids if e not in summary]
    if missing:
        out["no_data"] = missing
    if len(json.dumps(out, ensure_ascii=False, default=str)) > MAX_CHARS:
        for s in summary.values():
            s.pop("typical", None)
        notes.append("weekday times left out to keep the answer short: ask for fewer entities to see them")
    return _finish(out, notes, unknown)
