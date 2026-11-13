"""Attachments: photos, PDFs and text files sent to Jarvis and the agents."""

import asyncio
import io
import time
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from hubnex.attachments import AttachmentError, Attachments, note
from hubnex.main import create_app
from tests.conftest import response, text_block, tool_block


def photo(size=(3000, 2000), fmt="JPEG", mode="RGB", exif_rotate=False) -> bytes:
    img = Image.new(mode, size, (200, 30, 30) if mode == "RGB" else (200, 30, 30, 120))
    out = io.BytesIO()
    if exif_rotate:
        exif = Image.Exif()
        exif[0x0112] = 6  # taken with the phone turned: must be rotated 90°
        img.save(out, fmt, exif=exif)
    else:
        img.save(out, fmt)
    return out.getvalue()


def pdf(pages=2) -> bytes:
    out = io.BytesIO()
    imgs = [Image.new("RGB", (200, 280), "white") for _ in range(pages)]
    imgs[0].save(out, "PDF", save_all=True, append_images=imgs[1:])
    return out.getvalue()


def kinds(content):
    return [b["type"] for b in content] if isinstance(content, list) else ["str"]


def test_photos_are_turned_and_scaled(tmp_path):
    files = Attachments(tmp_path)
    att = files.save(photo(exif_rotate=True), "cantiere.jpg", "image/jpeg")
    assert att.kind == "image" and att.name == "cantiere.jpg"
    img = Image.open(files.path(att))
    assert img.size == (1045, 1568)  # rotated as taken, long side 1568
    png = files.save(photo((400, 300), "PNG", "RGBA"), "schermata.png", "image/png")
    assert Image.open(files.path(png)).mode == "RGB"
    assert files.get(att.id) == att and files.get("#" + att.id.upper()) == att
    assert files.get("../../etc/passwd") is None


def test_pdfs_text_and_unsupported_files(tmp_path):
    files = Attachments(tmp_path)
    doc = files.save(pdf(3), "computo.pdf", "application/pdf")
    assert (doc.kind, doc.pages) == ("pdf", 3)
    txt = files.save("Voce;Quantità\nCalcestruzzo;12".encode("cp1252"), "misure.csv", "text/csv")
    assert txt.kind == "text" and "Quantità" in files.path(txt).read_text(encoding="utf-8")
    with pytest.raises(AttachmentError, match="format not supported"):
        files.save(b"PK\x03\x04 a zip", "progetto.dwg", "application/octet-stream")
    with pytest.raises(AttachmentError, match="damaged"):
        files.save(b"%PDF-1.7 broken", "rotto.pdf")
    with pytest.raises(AttachmentError, match="empty file"):
        files.save(b"", "x.jpg")
    blocks = files.blocks([doc, txt])
    assert [b["type"] for b in blocks] == ["text", "document", "text", "document"]
    assert blocks[1]["source"]["media_type"] == "application/pdf"
    assert blocks[3]["source"] == {"type": "text", "media_type": "text/plain", "data": files.path(txt).read_text(encoding="utf-8")}
    assert note([doc]) == f"[Allegati: #{doc.id} «computo.pdf» (PDF, 3 pag.)]"


def test_old_attachments_are_deleted(tmp_path):
    files = Attachments(tmp_path)
    att = files.save(photo((100, 100)), "a.jpg")
    assert files.cleanup(now=time.time() + 31 * 86400) == 1
    assert files.get(att.id) is None and not list(tmp_path.iterdir())


async def test_jarvis_sees_the_photo_once_and_hands_it_to_the_agent(make_hq):
    hq = make_hq([])
    att = hq.attachments.save(photo(), "crepa.jpg", "image/jpeg")
    hq.client.responses = [
        response([tool_block("delegate", {"agent_id": "technical", "task": "Valuta la crepa", "allegati": [att.id]})], "tool_use"),
        response([text_block("Crepa superficiale.")], "end_turn"),  # tecnico
        response([text_block("Nulla di grave, signore.")], "end_turn"),  # jarvis
        response([text_block("Prego.")], "end_turn"),
    ]
    reply, _, by = await hq.converse("dashboard", "Guarda questa crepa", quick=True, local=True, attachments=[att])
    assert (reply, by) == ("Nulla di grave, signore.", "jarvis")  # never the quick route

    jarvis = hq.client.requests[0]["messages"][-1]["content"]
    assert kinds(jarvis) == ["text", "image", "text"]
    assert f"#{att.id}" in jarvis[-1]["text"] and "Guarda questa crepa" in jarvis[-1]["text"]
    agent = hq.client.requests[1]["messages"][0]["content"]
    assert kinds(agent) == ["text", "image", "text"] and "Valuta la crepa" in agent[-1]["text"]
    assert any(t["name"] == "view_attachment" for t in hq.client.requests[1]["tools"])

    # The next turn: only the note with the id, the photo is not sent again.
    await hq.converse("dashboard", "Grazie")
    msgs = hq.client.requests[-1]["messages"]
    assert all(isinstance(m["content"], str) for m in msgs)
    assert f"[Allegati: #{att.id} «crepa.jpg» (foto)]" in msgs[0]["content"]


async def test_only_files_and_unknown_ids(make_hq):
    hq = make_hq([
        response([tool_block("delegate", {"agent_id": "technical", "task": "x", "allegati": ["deadbeef"]})], "tool_use"),
        response([text_block("Cosa devo guardare?")], "end_turn"),
    ])
    att = hq.attachments.save(pdf(1), "verbale.pdf")
    await hq.converse("telegram:1", "", attachments=[att])
    first = hq.client.requests[0]["messages"][-1]["content"]
    assert kinds(first) == ["text", "document", "text"] and "Nessun testo" in first[-1]["text"]
    result = hq.client.requests[1]["messages"][-1]["content"][0]
    assert "Allegati non trovati: deadbeef" in result["content"]


async def test_an_agent_can_look_at_an_attachment_again(make_hq):
    hq = make_hq([])
    att = hq.attachments.save(photo((300, 200)), "quadro.jpg")
    hq.client.responses = [
        response([tool_block("view_attachment", {"id": att.id})], "tool_use"),
        response([text_block("Il quadro è in ordine.")], "end_turn"),
    ]
    assert await hq.run_agent("technical", "Com'era il quadro elettrico?") == "Il quadro è in ordine."
    result = hq.client.requests[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and kinds(result["content"]) == ["text", "image"]


def test_dashboard_uploads_and_sends(settings, make_hq):
    hq = make_hq([response([text_block("Ricevuto il verbale.")], "end_turn")])
    app = create_app(settings, hq=hq, start_workers=False)
    with TestClient(app) as client:
        r = client.post("/api/attachments?name=verbale.pdf", content=pdf(2), headers={"Content-Type": "application/pdf"})
        assert r.status_code == 200
        up = r.json()
        assert (up["name"], up["kind"], up["pages"]) == ("verbale.pdf", "pdf", 2)
        r = client.post("/api/attachments?name=x.exe", content=b"MZ\x90\x00", headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 422
        assert client.post("/api/chat", json={"text": "  "}).status_code == 422
        assert client.post("/api/chat", json={"text": "x", "attachments": ["00000000"]}).status_code == 404
        r = client.post("/api/chat", json={"text": "", "attachments": [up["id"]]})
        assert r.json()["reply"] == "Ricevuto il verbale."
        got = client.get(f"/api/attachments/{up['id']}")
        assert got.headers["content-type"] == "application/pdf" and got.content[:5] == b"%PDF-"


async def test_telegram_album_goes_to_whoever_it_is_for(make_hq, settings, monkeypatch):
    """An album arrives as one message per photo, to every bot in the group; only the first
    has the caption. The agent it is @addressed to answers with all the photos, Jarvis not."""
    from hubnex.integrations import telegram as tg

    monkeypatch.setattr(tg, "ALBUM_WAIT", 0.05)
    settings.telegram_chat_id = "-100"
    team = tg.TelegramTeam.__new__(tg.TelegramTeam)
    team.settings, team.hq, team._albums = settings, make_hq([]), {}
    team.apps = {"jarvis": NS(bot=NS(id=1, username="jarvis_bot")), "technical": NS(bot=NS(id=2, username="tecnico_bot"))}
    team.allowed = lambda update: True
    delivered = []

    async def deliver(agent_id, update, ctx, text, files):
        delivered.append((agent_id, text, len(files)))

    async def download(msg, ctx):
        return team.hq.attachments.save(photo((50, 50)), "foto.jpg")

    team._deliver, team._download = deliver, download
    chat = NS(id=-100, type="supergroup")

    def update(caption=None):
        msg = NS(media_group_id="g1", caption=caption, text=None, reply_to_message=None, photo=[1], document=None)
        return NS(effective_message=msg, effective_chat=chat)

    album = [update("@tecnico_bot guarda le fondazioni"), update(), update()]
    for key in ("jarvis", "technical"):
        for u in album:
            await team._file_handler(key)(u, NS(bot=team.apps[key].bot))
    await asyncio.sleep(0.2)
    assert delivered == [("technical", "guarda le fondazioni", 3)]
