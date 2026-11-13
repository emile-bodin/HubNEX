"""SQLite persistence: activity log, agent tasks, deadlines, memory notes, chat history."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    agent_id TEXT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    task TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    created REAL NOT NULL,
    finished REAL
);
CREATE TABLE IF NOT EXISTS deadlines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    due TEXT NOT NULL,
    company TEXT,
    agent_id TEXT,
    notes TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    notified INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    scope TEXT NOT NULL,
    topic TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER NOT NULL,
    body TEXT NOT NULL,
    reply_all INTEGER NOT NULL DEFAULT 0,
    to_addr TEXT NOT NULL,
    subject TEXT NOT NULL,
    chat_id INTEGER,
    msg_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    agent_id TEXT,
    summary TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    result TEXT,
    chat_id INTEGER,
    msg_id INTEGER,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_daily (
    day TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    model TEXT NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (day, agent_id, model)
);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    channel TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    updated REAL NOT NULL,
    deleted_at REAL
);
CREATE INDEX IF NOT EXISTS chat_sessions_channel ON chat_sessions (channel, updated);
CREATE TABLE IF NOT EXISTS ha_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    agent_id TEXT,
    channel TEXT,
    session_id TEXT,
    service TEXT NOT NULL,
    entities TEXT NOT NULL DEFAULT '',
    data TEXT,
    result TEXT
);
"""

# The kinds of rows a conversation's transcript holds. Only "text" rows are the conversation
# the model reads back; the others are how it got there (shown, never sent as context).
CHAT_KINDS = ("text", "tool", "tool_result", "thinking", "notice")
TITLE_CHARS = 80


def chat_title(text: str) -> str:
    """A conversation's title: its first line of real words, without the dashboard's
    "[I'm in the room ...]" note, cut to TITLE_CHARS."""
    text = re.sub(r"^\s*\[[^\]]*\]\s*", "", text or "").strip()
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line if len(line) <= TITLE_CHARS else line[: TITLE_CHARS - 1].rstrip() + "…"



class Store:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()
        self._lock = asyncio.Lock()

    def _migrate(self) -> None:
        """Columns added after the first release (existing databases lack them)."""
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(memory)")}
        if "agent_id" not in cols:
            self._conn.execute("ALTER TABLE memory ADD COLUMN agent_id TEXT")
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(chat)")}
        if "session_id" not in cols:  # 1.23: conversations (sessions) instead of one log per channel
            self._conn.execute("ALTER TABLE chat ADD COLUMN session_id TEXT")
            self._conn.execute("ALTER TABLE chat ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'")
            self._conn.execute("ALTER TABLE chat ADD COLUMN data TEXT")
        self._conn.execute("CREATE INDEX IF NOT EXISTS chat_session ON chat (session_id, id)")
        # What was there before sessions becomes one conversation per channel, the active one.
        for (channel,) in self._conn.execute("SELECT DISTINCT channel FROM chat WHERE session_id IS NULL").fetchall():
            first, last = self._conn.execute(
                "SELECT MIN(ts), MAX(ts) FROM chat WHERE channel=? AND session_id IS NULL", (channel,)
            ).fetchone()
            row = self._conn.execute(
                "SELECT text FROM chat WHERE channel=? AND session_id IS NULL AND role='user' ORDER BY id LIMIT 1",
                (channel,),
            ).fetchone()
            sid = uuid.uuid4().hex[:16]
            self._conn.execute(
                "INSERT INTO chat_sessions (id, channel, title, created, updated) VALUES (?,?,?,?,?)",
                (sid, channel, chat_title(row[0]) if row else "", first, last),
            )
            self._conn.execute("UPDATE chat SET session_id=? WHERE channel=? AND session_id IS NULL", (sid, channel))
            self._set_active(self._conn, channel, sid)

    async def _run(self, sql: str, params: tuple = (), *, fetch: bool = False) -> Any:
        async with self._lock:
            def work():
                cur = self._conn.execute(sql, params)
                self._conn.commit()
                if fetch:
                    return [dict(r) for r in cur.fetchall()]
                return cur.lastrowid

            return await asyncio.to_thread(work)

    async def _tx(self, fn) -> Any:
        """Several statements as one transaction: fn(conn) runs under the lock, then commits."""
        async with self._lock:
            def work():
                try:
                    out = fn(self._conn)
                    self._conn.commit()
                    return out
                except Exception:
                    self._conn.rollback()
                    raise

            return await asyncio.to_thread(work)

    # --- Claude spend, one row per day, agent and model --------------------
    async def usage_add(self, day: str, agent_id: str, model: str, tokens_in: int, tokens_out: int, cost: float) -> None:
        await self._run(
            "INSERT INTO usage_daily (day, agent_id, model, calls, tokens_in, tokens_out, cost) VALUES (?,?,?,1,?,?,?) "
            "ON CONFLICT(day, agent_id, model) DO UPDATE SET calls=calls+1, tokens_in=tokens_in+excluded.tokens_in, "
            "tokens_out=tokens_out+excluded.tokens_out, cost=cost+excluded.cost",
            (day, agent_id, model, tokens_in, tokens_out, cost),
        )

    async def usage_by(self, column: str, since: str, until: str = "9999") -> list[dict]:
        """Spend from day `since` to `until` (included) grouped by day, agent_id or model."""
        if column not in ("day", "agent_id", "model"):
            raise ValueError(column)
        return await self._run(
            f"SELECT {column} AS key, SUM(calls) AS calls, SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out, "
            f"SUM(cost) AS cost FROM usage_daily WHERE day >= ? AND day <= ? GROUP BY {column} ORDER BY "
            + ("day" if column == "day" else "cost DESC"),
            (since, until),
            fetch=True,
        )

    # --- log -------------------------------------------------------------
    async def log(self, kind: str, text: str, agent_id: str | None = None) -> dict:
        ts = time.time()
        rid = await self._run(
            "INSERT INTO logs (ts, agent_id, kind, text) VALUES (?,?,?,?)", (ts, agent_id, kind, text)
        )
        return {"id": rid, "ts": ts, "agent_id": agent_id, "kind": kind, "text": text}

    async def recent_logs(self, limit: int = 80, before_id: int | None = None) -> list[dict]:
        if before_id:
            rows = await self._run(
                "SELECT * FROM logs WHERE id < ? ORDER BY id DESC LIMIT ?", (before_id, limit), fetch=True
            )
        else:
            rows = await self._run("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,), fetch=True)
        return list(reversed(rows))

    # --- tasks -----------------------------------------------------------
    async def task_start(self, agent_id: str, task: str, source: str) -> int:
        return await self._run(
            "INSERT INTO tasks (agent_id, task, source, status, created) VALUES (?,?,?,?,?)",
            (agent_id, task, source, "running", time.time()),
        )

    async def task_finish(self, task_id: int, status: str, result: str) -> None:
        await self._run(
            "UPDATE tasks SET status=?, result=?, finished=? WHERE id=?",
            (status, result, time.time(), task_id),
        )

    async def agent_tasks(self, agent_id: str, limit: int = 10) -> list[dict]:
        return await self._run(
            "SELECT * FROM tasks WHERE agent_id=? ORDER BY id DESC LIMIT ?", (agent_id, limit), fetch=True
        )

    async def task_counts(self) -> dict[str, int]:
        rows = await self._run(
            "SELECT agent_id, COUNT(*) AS n FROM tasks WHERE status='done' GROUP BY agent_id", fetch=True
        )
        return {r["agent_id"]: r["n"] for r in rows}

    # --- deadlines -------------------------------------------------------
    async def deadline_add(
        self, title: str, due: str, company: str | None = None, agent_id: str | None = None, notes: str = ""
    ) -> int:
        return await self._run(
            "INSERT INTO deadlines (title, due, company, agent_id, notes, created) VALUES (?,?,?,?,?,?)",
            (title, due, company, agent_id, notes, time.time()),
        )

    async def deadlines(self, include_done: bool = False) -> list[dict]:
        where = "" if include_done else "WHERE done=0"
        return await self._run(f"SELECT * FROM deadlines {where} ORDER BY due ASC", fetch=True)

    async def deadline_done(self, deadline_id: int) -> None:
        await self._run("UPDATE deadlines SET done=1 WHERE id=?", (deadline_id,))

    async def deadline_mark_notified(self, deadline_id: int) -> None:
        await self._run("UPDATE deadlines SET notified=1 WHERE id=?", (deadline_id,))

    # --- memory ----------------------------------------------------------
    async def remember(self, scope: str, topic: str, content: str, agent_id: str | None = None) -> int:
        return await self._run(
            "INSERT INTO memory (ts, scope, topic, content, agent_id) VALUES (?,?,?,?,?)",
            (time.time(), scope, topic, content, agent_id),
        )

    # --- neural map ------------------------------------------------------
    async def memories(self, limit: int = 400) -> list[dict]:
        return await self._run("SELECT * FROM memory ORDER BY id DESC LIMIT ?", (limit,), fetch=True)

    async def recent_tasks(self, limit: int = 200) -> list[dict]:
        return await self._run(
            "SELECT id, agent_id, task, status, result, created FROM tasks ORDER BY id DESC LIMIT ?", (limit,), fetch=True
        )

    async def recall(self, query: str, scope: str | None = None, limit: int = 10) -> list[dict]:
        like = f"%{query}%"
        if scope:
            return await self._run(
                "SELECT * FROM memory WHERE scope IN (?, 'global') AND (topic LIKE ? OR content LIKE ?) "
                "ORDER BY id DESC LIMIT ?",
                (scope, like, like, limit),
                fetch=True,
            )
        return await self._run(
            "SELECT * FROM memory WHERE topic LIKE ? OR content LIKE ? ORDER BY id DESC LIMIT ?",
            (like, like, limit),
            fetch=True,
        )

    async def memory_count(self) -> int:
        rows = await self._run("SELECT COUNT(*) AS n FROM memory", fetch=True)
        return rows[0]["n"]

    # --- chat: conversations (sessions) and their transcripts -------------
    @staticmethod
    def _new_session(conn, channel: str, title: str = "") -> str:
        sid = uuid.uuid4().hex[:16]
        now = time.time()
        conn.execute(
            "INSERT INTO chat_sessions (id, channel, title, created, updated) VALUES (?,?,?,?,?)",
            (sid, channel, title, now, now),
        )
        return sid

    @staticmethod
    def _set_active(conn, channel: str, sid: str) -> None:
        conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (f"chat_active:{channel}", json.dumps(sid)),
        )

    @staticmethod
    def _active(conn, channel: str) -> str | None:
        row = conn.execute("SELECT value FROM kv WHERE key=?", (f"chat_active:{channel}",)).fetchone()
        if not row:
            return None
        sid = json.loads(row[0])
        ok = conn.execute("SELECT 1 FROM chat_sessions WHERE id=? AND deleted_at IS NULL", (sid,)).fetchone()
        return sid if ok else None

    async def session_active(self, channel: str) -> str | None:
        """The channel's current conversation, if it has one that was not deleted."""
        return await self._tx(lambda c: self._active(c, channel))

    async def session_ensure(self, channel: str) -> str:
        """The channel's current conversation, started when there is none."""
        def work(c):
            sid = self._active(c, channel)
            if sid is None:
                sid = self._new_session(c, channel)
                self._set_active(c, channel, sid)
            return sid

        return await self._tx(work)

    async def session_new(self, channel: str, title: str = "", activate: bool = True) -> str:
        def work(c):
            sid = self._new_session(c, channel, title)
            if activate:
                self._set_active(c, channel, sid)
            return sid

        return await self._tx(work)

    async def session_set_active(self, channel: str, sid: str) -> None:
        await self._tx(lambda c: self._set_active(c, channel, sid))

    _SESSION_COLS = (
        "s.id, s.channel, s.title, s.created, s.updated, s.deleted_at, "
        "(SELECT COUNT(*) FROM chat m WHERE m.session_id=s.id AND m.kind='text') AS messages, "
        "(SELECT m.text FROM chat m WHERE m.session_id=s.id AND m.kind='text' ORDER BY m.id DESC LIMIT 1) AS last"
    )

    async def session_get(self, sid: str) -> dict | None:
        rows = await self._run(f"SELECT {self._SESSION_COLS} FROM chat_sessions s WHERE s.id=?", (sid,), fetch=True)
        return rows[0] if rows else None

    async def sessions(self, channel: str | None = None, deleted: bool = False, limit: int = 100) -> list[dict]:
        """Conversations, most recently active first; with `deleted` only the ones in the trash."""
        where = ["s.deleted_at IS NOT NULL" if deleted else "s.deleted_at IS NULL"]
        params: list[Any] = []
        if channel:
            where.append("s.channel=?")
            params.append(channel)
        params.append(limit)
        return await self._run(
            f"SELECT {self._SESSION_COLS} FROM chat_sessions s WHERE {' AND '.join(where)} "
            "ORDER BY s.updated DESC LIMIT ?", tuple(params), fetch=True,
        )

    async def session_rename(self, sid: str, title: str) -> bool:
        def work(c):
            return c.execute("UPDATE chat_sessions SET title=? WHERE id=?", (title.strip()[:120], sid)).rowcount > 0

        return await self._tx(work)

    async def session_delete(self, sid: str) -> bool:
        """Into the trash (kept chat_trash_days, see session_purge): restore puts it back."""
        def work(c):
            return c.execute(
                "UPDATE chat_sessions SET deleted_at=? WHERE id=? AND deleted_at IS NULL", (time.time(), sid)
            ).rowcount > 0

        return await self._tx(work)

    async def session_restore(self, sid: str) -> bool:
        def work(c):
            return c.execute(
                "UPDATE chat_sessions SET deleted_at=NULL WHERE id=? AND deleted_at IS NOT NULL", (sid,)
            ).rowcount > 0

        return await self._tx(work)

    async def session_purge(self, trash_days: float = 7, keep: int = 200) -> int:
        """Forget for good what has been in the trash longer than `trash_days`, and the oldest
        conversations of a channel beyond `keep` (never the channel's active one)."""
        def work(c):
            gone = [r[0] for r in c.execute(
                "SELECT id FROM chat_sessions WHERE deleted_at IS NOT NULL AND deleted_at < ?",
                (time.time() - trash_days * 86400,),
            )]
            for (channel,) in c.execute("SELECT DISTINCT channel FROM chat_sessions").fetchall():
                active = self._active(c, channel)
                rows = c.execute(
                    "SELECT id FROM chat_sessions WHERE channel=? AND deleted_at IS NULL ORDER BY updated DESC",
                    (channel,),
                ).fetchall()
                gone += [r[0] for r in rows[keep:] if r[0] != active]
            for sid in gone:
                c.execute("DELETE FROM chat WHERE session_id=?", (sid,))
                c.execute("DELETE FROM chat_sessions WHERE id=?", (sid,))
            return len(gone)

        return await self._tx(work)

    async def chat_add(
        self, channel: str, role: str, text: str, session_id: str | None = None,
        kind: str = "text", data: Any = None,
    ) -> dict:
        """A row of a conversation (the channel's current one when `session_id` is None).
        The first thing the owner says names the conversation. Returns the row as stored."""
        if kind not in CHAT_KINDS:
            raise ValueError(kind)

        def work(c):
            sid = session_id or self._active(c, channel)
            if sid is None:
                sid = self._new_session(c, channel)
                self._set_active(c, channel, sid)
            now = time.time()
            payload = json.dumps(data, ensure_ascii=False) if data is not None else None
            rid = c.execute(
                "INSERT INTO chat (ts, channel, role, text, session_id, kind, data) VALUES (?,?,?,?,?,?,?)",
                (now, channel, role, text, sid, kind, payload),
            ).lastrowid
            c.execute("UPDATE chat_sessions SET updated=? WHERE id=?", (now, sid))
            if role == "user" and kind == "text":
                c.execute("UPDATE chat_sessions SET title=? WHERE id=? AND title=''", (chat_title(text), sid))
            return {"id": rid, "ts": now, "session_id": sid, "role": role, "kind": kind, "text": text, "data": data}

        return await self._tx(work)

    async def chat_history(self, channel: str, limit: int = 20) -> list[dict]:
        """The last `limit` messages of the channel's current conversation."""
        sid = await self.session_active(channel)
        return await self.session_history(sid, limit) if sid else []

    async def session_history(self, sid: str, limit: int = 20) -> list[dict]:
        """What was said in a conversation (the model's context): the last `limit` messages."""
        rows = await self._run(
            "SELECT role, text FROM chat WHERE session_id=? AND kind='text' ORDER BY id DESC LIMIT ?",
            (sid, limit), fetch=True,
        )
        return list(reversed(rows))

    async def session_transcript(self, sid: str, before_id: int | None = None, limit: int = 200) -> list[dict]:
        """Every row of a conversation, oldest first, for repainting it: the newest `limit`
        (older than `before_id` when given, for paging back)."""
        sql = "SELECT id, ts, role, kind, text, data FROM chat WHERE session_id=?"
        params: list[Any] = [sid]
        if before_id:
            sql += " AND id < ?"
            params.append(before_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = await self._run(sql, tuple(params), fetch=True)
        for r in rows:
            r["data"] = json.loads(r["data"]) if r["data"] else None
        return list(reversed(rows))

    # --- what HubNEX did in the house ---------------------------------------
    async def ha_action_add(
        self, service: str, entities: list[str], data: Any = None, result: str = "",
        agent_id: str | None = None, channel: str | None = None, session_id: str | None = None,
    ) -> dict:
        now = time.time()
        rid = await self._run(
            "INSERT INTO ha_actions (ts, agent_id, channel, session_id, service, entities, data, result) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (now, agent_id, channel, session_id, service, ",".join(entities),
             json.dumps(data, ensure_ascii=False, default=str) if data is not None else None, result[:500]),
        )
        return {"id": rid, "ts": now, "agent_id": agent_id, "channel": channel, "session_id": session_id,
                "service": service, "entities": entities, "result": result[:500]}

    async def ha_actions(self, limit: int = 100, entity: str | None = None) -> list[dict]:
        sql, params = "SELECT * FROM ha_actions", []
        if entity:
            sql += " WHERE ',' || entities || ',' LIKE ?"
            params.append(f"%,{entity},%")
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = await self._run(sql, tuple(params), fetch=True)
        for r in rows:
            r["entities"] = [e for e in (r["entities"] or "").split(",") if e]
            r["data"] = json.loads(r["data"]) if r["data"] else None
        return rows

    async def ha_actions_purge(self, days: float = 30) -> None:
        await self._run("DELETE FROM ha_actions WHERE ts < ?", (time.time() - days * 86400,))

    # --- key/value state --------------------------------------------------
    async def get(self, key: str, default: Any = None) -> Any:
        rows = await self._run("SELECT value FROM kv WHERE key=?", (key,), fetch=True)
        return json.loads(rows[0]["value"]) if rows else default

    async def put(self, key: str, value: Any) -> None:
        await self._run(
            "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )

    # --- email drafts awaiting approval -------------------------------------
    async def draft_add(self, uid: int, body: str, reply_all: bool, to_addr: str, subject: str) -> int:
        return await self._run(
            "INSERT INTO drafts (uid, body, reply_all, to_addr, subject, created) VALUES (?,?,?,?,?,?)",
            (uid, body, int(reply_all), to_addr, subject, time.time()),
        )

    async def draft_set_message(self, draft_id: int, chat_id: int, msg_id: int) -> None:
        await self._run("UPDATE drafts SET chat_id=?, msg_id=? WHERE id=?", (chat_id, msg_id, draft_id))

    async def draft(self, draft_id: int) -> dict | None:
        rows = await self._run("SELECT * FROM drafts WHERE id=?", (draft_id,), fetch=True)
        return rows[0] if rows else None

    async def draft_by_message(self, chat_id: int, msg_id: int) -> dict | None:
        rows = await self._run(
            "SELECT * FROM drafts WHERE chat_id=? AND msg_id=? AND status='open'", (chat_id, msg_id), fetch=True
        )
        return rows[0] if rows else None

    async def draft_claim(self, draft_id: int) -> bool:
        """Atomically take an open draft for an action, so two clicks can't send it twice."""
        async with self._lock:
            def work():
                cur = self._conn.execute("UPDATE drafts SET status='busy' WHERE id=? AND status='open'", (draft_id,))
                self._conn.commit()
                return cur.rowcount == 1

            return await asyncio.to_thread(work)

    async def draft_close(self, draft_id: int, status: str) -> None:
        await self._run("UPDATE drafts SET status=? WHERE id=?", (status, draft_id))

    async def drafts_open(self) -> list[dict]:
        return await self._run("SELECT * FROM drafts WHERE status='open' ORDER BY id DESC", fetch=True)

    # --- actions on connected programs awaiting confirmation -----------------
    async def action_add(self, kind: str, agent_id: str | None, summary: str, payload: dict) -> int:
        return await self._run(
            "INSERT INTO actions (kind, agent_id, summary, payload, created) VALUES (?,?,?,?,?)",
            (kind, agent_id, summary, json.dumps(payload), time.time()),
        )

    async def action(self, action_id: int) -> dict | None:
        rows = await self._run("SELECT * FROM actions WHERE id=?", (action_id,), fetch=True)
        if not rows:
            return None
        row = rows[0]
        row["payload"] = json.loads(row["payload"])
        return row

    async def action_set_message(self, action_id: int, chat_id: int, msg_id: int) -> None:
        await self._run("UPDATE actions SET chat_id=?, msg_id=? WHERE id=?", (chat_id, msg_id, action_id))

    async def action_claim(self, action_id: int) -> bool:
        """Atomically take an open action, so two clicks can't run it twice."""
        async with self._lock:
            def work():
                cur = self._conn.execute("UPDATE actions SET status='busy' WHERE id=? AND status='open'", (action_id,))
                self._conn.commit()
                return cur.rowcount == 1

            return await asyncio.to_thread(work)

    async def action_close(self, action_id: int, status: str, result: str | None = None) -> None:
        await self._run("UPDATE actions SET status=?, result=? WHERE id=?", (status, result, action_id))

    async def actions_open(self) -> list[dict]:
        rows = await self._run(
            "SELECT id, kind, agent_id, summary, created FROM actions WHERE status='open' ORDER BY id DESC", fetch=True
        )
        return rows
