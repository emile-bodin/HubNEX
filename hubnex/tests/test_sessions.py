"""Conversations (sessions): several per channel, each with its own context and transcript."""

from __future__ import annotations

import asyncio
import sqlite3
import time

from fastapi.testclient import TestClient

from tests.conftest import response, text_block, tool_block
from hubnex.llm import RunGate
from hubnex.main import create_app
from hubnex.store import Store, chat_title


def user_texts(request) -> list[str]:
    """What the model was sent as the owner's words, in order."""
    out = []
    for m in request["messages"]:
        if m["role"] != "user":
            continue
        content = m["content"]
        out.append(content if isinstance(content, str) else " ".join(
            b.get("text", "") for b in content if isinstance(b, dict)))
    return out


def test_title_drops_the_room_note_and_is_short():
    assert chat_title("[Sono in cucina]\n\nAccendi la luce") == "Accendi la luce"
    assert len(chat_title("x" * 200)) == 80


def test_old_chat_rows_become_one_conversation_per_channel(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE chat (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, "
                 "channel TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL)")
    conn.executemany("INSERT INTO chat (ts, channel, role, text) VALUES (?,?,?,?)", [
        (1.0, "dashboard", "user", "Che tempo fa?"), (2.0, "dashboard", "assistant", "Sole."),
        (3.0, "telegram:-100", "user", "Ciao"),
    ])
    conn.commit()
    conn.close()

    async def check():
        store = Store(str(db))
        sid = await store.session_active("dashboard")
        assert sid and sid != await store.session_active("telegram:-100")
        sess = await store.session_get(sid)
        assert sess["title"] == "Che tempo fa?" and sess["messages"] == 2
        assert [h["text"] for h in await store.chat_history("dashboard")] == ["Che tempo fa?", "Sole."]

    asyncio.run(check())


async def test_a_new_conversation_starts_without_the_old_context(make_hq):
    hq = make_hq([response([text_block("Primo.")], "end_turn"), response([text_block("Secondo.")], "end_turn")])
    await hq.converse("dashboard", "ricordati il numero 42")
    first = await hq.store.session_active("dashboard")
    second = await hq.new_session("dashboard")
    assert second != first and await hq.store.session_active("dashboard") == second
    await hq.converse("dashboard", "che numero ti ho detto?")
    sent = user_texts(hq.client.requests[1])
    assert len(sent) == 1 and "42" not in sent[0]
    # the old conversation is still there, and can be continued by name
    hq.client.responses.append(response([text_block("Era 42.")], "end_turn"))
    await hq.converse("dashboard", "e adesso?", session_id=first)
    assert any("42" in t for t in user_texts(hq.client.requests[2]))
    assert await hq.store.session_active("dashboard") == first


async def test_tool_steps_and_answer_are_in_the_transcript(make_hq):
    hq = make_hq([
        response([tool_block("memory_save", {"topic": "numero", "content": "42"})], "tool_use"),
        response([text_block("Salvato.")], "end_turn"),
    ])
    events = hq.subscribe()
    reply, _, by = await hq.converse("dashboard", "salva 42")
    assert (reply, by) == ("Salvato.", "jarvis")
    sid = await hq.store.session_active("dashboard")
    rows = await hq.store.session_transcript(sid)
    assert [(r["role"], r["kind"]) for r in rows] == [
        ("user", "text"), ("assistant", "tool"), ("assistant", "tool_result"), ("assistant", "text"),
    ]
    assert rows[1]["data"]["name"] == "memory_save" and rows[1]["data"]["input"]["content"] == "42"
    # the model's context is only what was said, never the tool steps
    assert [h["text"] for h in await hq.store.session_history(sid)] == ["salva 42", "Salvato."]
    seen = []
    while not events.empty():
        seen.append(events.get_nowait())
    assert {"chat", "chat_busy"} <= {e["type"] for e in seen}
    assert any(e["type"] == "chat_busy" and e["busy"] is False for e in seen)


async def test_tool_steps_are_not_kept_when_switched_off(make_hq):
    hq = make_hq([
        response([tool_block("memory_save", {"topic": "a", "content": "b"})], "tool_use"),
        response([text_block("Ok.")], "end_turn"),
    ])
    hq.settings.chat_show_tools = False
    await hq.converse("dashboard", "salva")
    rows = await hq.store.session_transcript(await hq.store.session_active("dashboard"))
    assert [r["kind"] for r in rows] == ["text", "text"]


class _Slow:
    """A stream that never finishes by itself: only a stop ends it."""

    async def __aenter__(self):
        await asyncio.sleep(30)

    async def __aexit__(self, *exc):
        return False


async def test_stop_ends_the_turn_and_says_so(make_hq):
    hq = make_hq([])
    hq.client.beta.messages.stream = lambda **kw: _Slow()
    turn = asyncio.create_task(hq.converse("dashboard", "scrivi un romanzo"))
    for _ in range(100):
        sid = await hq.store.session_active("dashboard")
        if sid and hq.session_busy(sid):
            break
        await asyncio.sleep(0.01)
    assert await hq.stop_session(sid)
    assert await turn == ("", None, "stopped")
    assert not hq.session_busy(sid)
    rows = await hq.store.session_transcript(sid)
    assert rows[-1]["kind"] == "notice"
    assert hq.agents["jarvis"].status == "sleeping"
    assert not await hq.stop_session(sid)  # nothing left to stop


async def test_silence_starts_a_new_conversation(make_hq):
    hq = make_hq([response([text_block("Uno.")], "end_turn")])
    hq.settings.chat_new_session_after_hours = 2
    await hq.converse("telegram:-100", "ciao")
    old = await hq.store.session_active("telegram:-100")
    assert await hq.session_for("telegram:-100") == old  # still fresh
    await hq.store._run("UPDATE chat_sessions SET updated=? WHERE id=?", (time.time() - 3 * 3600, old))
    assert await hq.session_for("telegram:-100") != old


async def test_trash_restore_and_purge(make_hq):
    hq = make_hq([])
    store = hq.store
    sid = await store.session_new("dashboard", "da buttare")
    await store.chat_add("dashboard", "user", "x", session_id=sid)
    assert await store.session_delete(sid)
    assert await store.session_active("dashboard") is None  # the deleted one is no longer current
    assert [s["id"] for s in await store.sessions("dashboard", deleted=True)] == [sid]
    assert await store.session_restore(sid)
    assert await store.session_delete(sid)
    await store._run("UPDATE chat_sessions SET deleted_at=? WHERE id=?", (time.time() - 8 * 86400, sid))
    assert await store.session_purge(trash_days=7) == 1
    assert await store.session_get(sid) is None
    assert await store.session_transcript(sid) == []


async def test_run_gate_keeps_a_seat_for_a_person():
    gate = RunGate(2)
    order = []

    async def run(name, person, hold):
        async with gate.seat(person):
            order.append(name)
            await hold.wait()

    hold = asyncio.Event()
    routine1 = asyncio.create_task(run("routine1", False, hold))
    await asyncio.sleep(0.01)
    routine2 = asyncio.create_task(run("routine2", False, hold))  # must wait: the last seat is a person's
    person = asyncio.create_task(run("person", True, hold))
    await asyncio.sleep(0.01)
    assert order == ["routine1", "person"]
    hold.set()
    await asyncio.gather(routine1, routine2, person)
    assert order[-1] == "routine2"


def test_sessions_api(settings, make_hq):
    settings.hq_token = "t"
    hq = make_hq([response([text_block("Ciao!")], "end_turn"), response([text_block("Di nuovo.")], "end_turn")])
    hq.settings.model_voice = ""
    auth = {"Authorization": "Bearer t"}
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        first = client.post("/api/chat", headers=auth, json={"text": "buongiorno"}).json()["session_id"]
        listing = client.get("/api/chat/sessions", headers=auth).json()
        assert listing["active"] == first
        assert [s["title"] for s in listing["sessions"]] == ["buongiorno"]

        new = client.post("/api/chat/sessions", headers=auth, json={"channel": "dashboard"}).json()
        assert new["active"] and new["id"] != first
        out = client.post("/api/chat", headers=auth, json={"text": "altro", "session_id": new["id"]}).json()
        assert out["session_id"] == new["id"]

        view = client.get(f"/api/chat/sessions/{first}", headers=auth).json()
        assert [e["text"] for e in view["events"]] == ["buongiorno", "Ciao!"]
        assert view["session"]["active"] is False
        assert client.get(f"/api/chat/sessions/{first}?activate=true", headers=auth).json()["session"]["active"]

        assert client.patch(f"/api/chat/sessions/{first}", headers=auth, json={"title": "Saluti"}).json()["title"] == "Saluti"
        assert client.delete(f"/api/chat/sessions/{first}", headers=auth).json()["ok"]
        assert client.get(f"/api/chat/sessions/{first}", headers=auth).status_code == 404
        trash = client.get("/api/chat/sessions?trash=true", headers=auth).json()["sessions"]
        assert [s["id"] for s in trash] == [first]
        assert client.post(f"/api/chat/sessions/{first}/restore", headers=auth).json()["title"] == "Saluti"
        assert client.post(f"/api/chat/sessions/{first}/stop", headers=auth).json() == {"stopped": False}
        assert client.post("/api/chat", headers=auth, json={"text": "x", "session_id": "nope"}).status_code == 404
