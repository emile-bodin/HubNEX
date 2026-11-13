"""Backup and restore: moving HubNEX (memory, house, configuration) to another installation."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from hubnex.backup import BackupError, apply_pending_restore, make_backup, stage_restore
from hubnex.main import create_app
from hubnex.store import Store


async def test_backup_moves_everything_to_another_installation(tmp_path):
    old_db, old_cfg = tmp_path / "old" / "hubnex.db", tmp_path / "old" / "config"
    old_cfg.mkdir(parents=True)
    store = Store(str(old_db))
    await store.remember("work", "Cliente", "Il cliente chiede il preventivo a marzo", "technical")
    await store.put("casa_adjust", {"names": {"light.x": "Faretti"}})
    (old_cfg / "agents.yaml").write_text("boss: {name: Jarvis}\n")
    (old_cfg / "casa.yaml").write_text("floors: []\n")
    (old_cfg / "pianta-1.jpg").write_bytes(b"\xff\xd8jpg")
    (old_cfg / ".nascosto").write_text("no")

    data = make_backup(str(old_db), old_cfg, "1.9.0")
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert sorted(names) == ["config/agents.yaml", "config/casa.yaml", "config/pianta-1.jpg", "db/hubnex.db", "manifest.json"]

    # the new installation already has its own (default) files
    new_db, new_cfg = tmp_path / "new" / "hubnex.db", tmp_path / "new" / "config"
    new_cfg.mkdir(parents=True)
    (new_cfg / "agents.yaml").write_text("boss: {name: Default}\n")
    Store(str(new_db))
    manifest = stage_restore(data, str(new_db))
    assert manifest["version"] == "1.9.0"
    assert apply_pending_restore(str(new_db), new_cfg)["version"] == "1.9.0"
    assert apply_pending_restore(str(new_db), new_cfg) is None  # only once

    assert (new_cfg / "agents.yaml").read_text() == "boss: {name: Jarvis}\n"
    assert (new_cfg / "agents.yaml.prima-del-ripristino").read_text() == "boss: {name: Default}\n"
    assert (new_cfg / "pianta-1.jpg").read_bytes() == b"\xff\xd8jpg"
    restored = Store(str(new_db))
    assert await restored.get("casa_adjust", {}) == {"names": {"light.x": "Faretti"}}
    assert [m["content"] for m in await restored.memories()] == ["Il cliente chiede il preventivo a marzo"]
    # the copies kept by a restore are not exported again
    assert "config/agents.yaml.prima-del-ripristino" not in zipfile.ZipFile(io.BytesIO(make_backup(str(new_db), new_cfg, "x"))).namelist()


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


def test_bad_backups_are_refused(tmp_path):
    db = str(tmp_path / "hubnex.db")
    manifest = json.dumps({"app": "hubnex"})
    with pytest.raises(BackupError, match="zip"):
        stage_restore(b"not a zip", db)
    with pytest.raises(BackupError, match="manifest missing"):
        stage_restore(_zip({"config/agents.yaml": "x"}), db)
    with pytest.raises(BackupError, match="unexpected file"):
        stage_restore(_zip({"manifest.json": manifest, "config/../../etc/passwd": "x"}), db)
    with pytest.raises(BackupError, match="unexpected file"):
        stage_restore(_zip({"manifest.json": manifest, "altro/file": "x"}), db)
    with pytest.raises(BackupError, match="damaged"):
        stage_restore(_zip({"manifest.json": manifest, "db/hubnex.db": "non è sqlite"}), db)
    assert not (tmp_path / "restore-pending").exists()


def test_backup_endpoints(settings, make_hq, tmp_path):
    settings.casa_file = str(tmp_path / "cfg" / "casa.yaml")
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "casa.yaml").write_text("floors: []\n")
    hq = make_hq([])
    with TestClient(create_app(settings, hq=hq, start_workers=False)) as client:
        r = client.get("/api/backup")
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        assert "hubnex-backup-" in r.headers["content-disposition"]
        assert "config/casa.yaml" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        ok = client.post("/api/backup/restore", content=r.content)
        assert ok.status_code == 200 and ok.json()["restarting"] is False
        assert client.post("/api/backup/restore", content=b"zzz").status_code == 422


def test_database_files_in_the_config_folder_are_not_copied_raw(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "casa.yaml").write_text("x")
    (cfg / "hubnex.db").write_bytes(b"raw")
    (cfg / "hubnex.db-wal").write_bytes(b"raw")
    names = zipfile.ZipFile(io.BytesIO(make_backup(str(tmp_path / "none.db"), cfg, "x"))).namelist()
    assert names == ["manifest.json", "config/casa.yaml"]
