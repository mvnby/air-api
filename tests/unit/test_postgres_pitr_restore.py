import hashlib
import importlib.util
import io
import json
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/ha/restore_postgres_pitr_from_s3.py"
SPEC = importlib.util.spec_from_file_location("restore_postgres_pitr_from_s3", MODULE_PATH)
pitr_restore = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = pitr_restore
SPEC.loader.exec_module(pitr_restore)


class FakeConfig:
    bucket = "private-pitr"
    key_prefix = "postgres/pitr"
    cluster = "mvn-api"


class FakeBody:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self):
        return self.payload


class FakePaginator:
    def __init__(self, keys):
        self.keys = keys

    def paginate(self, **kwargs):
        prefix = kwargs["Prefix"]
        return [
            {
                "Contents": [
                    {"Key": key, "LastModified": datetime(2026, 7, 2, tzinfo=timezone.utc)}
                    for key in self.keys
                    if key.startswith(prefix)
                ]
            }
        ]


class FakeClient:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.downloads = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(list(self.objects))

    def get_object(self, *, Bucket, Key):
        assert Bucket == FakeConfig.bucket
        return {"Body": FakeBody(self.objects[Key])}

    def download_file(self, bucket, key, filename):
        assert bucket == FakeConfig.bucket
        Path(filename).write_bytes(self.objects[key])
        self.downloads.append((key, filename))


def _tar_gz(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _manifest(backup_id: str, created_at: str, files: list[dict]) -> bytes:
    return json.dumps(
        {
            "backup_id": backup_id,
            "created_at": created_at,
            "cluster": "mvn-api",
            "files": files,
        }
    ).encode("utf-8")


def _file_entry(backup_id: str, name: str, content: bytes) -> dict:
    return {
        "name": name,
        "key": f"postgres/pitr/mvn-api/basebackups/{backup_id}/{name}",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def test_load_python_module_from_path_supports_extensionless_helper(tmp_path):
    helper = tmp_path / "mvn-postgres-pitr-upload"
    helper.write_text(
        "def build_client(config):\n"
        "    return ('client', config)\n"
        "def load_config():\n"
        "    return 'config'\n"
        "def sha256_file(path):\n"
        "    return 'sha256'\n",
        encoding="utf-8",
    )

    module = pitr_restore._load_python_module_from_path(
        "test_extensionless_pitr_upload_helper",
        helper,
    )

    assert module is not None
    assert module.load_config() == "config"
    assert module.build_client("cfg") == ("client", "cfg")
    assert module.sha256_file("/tmp/file") == "sha256"


def test_select_manifest_uses_latest_basebackup_before_target_time():
    manifests = [
        pitr_restore.BasebackupManifest(
            backup_id="old",
            created_at=datetime(2026, 7, 2, 1, tzinfo=timezone.utc),
            key="old/manifest.json",
            payload={"files": []},
        ),
        pitr_restore.BasebackupManifest(
            backup_id="new",
            created_at=datetime(2026, 7, 2, 3, tzinfo=timezone.utc),
            key="new/manifest.json",
            payload={"files": []},
        ),
    ]

    selected = pitr_restore.select_manifest(
        manifests,
        target_time=datetime(2026, 7, 2, 2, tzinfo=timezone.utc),
    )

    assert selected.backup_id == "old"


def test_prepare_downloads_extracts_and_writes_recovery_files(monkeypatch, tmp_path):
    base_tar = _tar_gz({"PG_VERSION": b"15\n", "postgresql.conf": b""})
    wal_tar = _tar_gz({"00000001000000000000000A": b"wal"})
    metadata = b'{"backup_id":"backup-1"}'
    files = [
        _file_entry("backup-1", "base.tar.gz", base_tar),
        _file_entry("backup-1", "pg_wal.tar.gz", wal_tar),
        _file_entry("backup-1", "metadata.json", metadata),
    ]
    objects = {
        "postgres/pitr/mvn-api/basebackups/backup-1/manifest.json": _manifest(
            "backup-1",
            "2026-07-02T01:00:00+00:00",
            files,
        ),
        "postgres/pitr/mvn-api/basebackups/backup-1/base.tar.gz": base_tar,
        "postgres/pitr/mvn-api/basebackups/backup-1/pg_wal.tar.gz": wal_tar,
        "postgres/pitr/mvn-api/basebackups/backup-1/metadata.json": metadata,
        "postgres/pitr/mvn-api/wal/00000001/00000001000000000000000B": b"archived-wal",
    }
    client = FakeClient(objects)
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda config: client)

    exit_code = pitr_restore.main(
        [
            "prepare",
            "--target-dir",
            str(tmp_path / "restore"),
            "--backup-id",
            "backup-1",
            "--target-time",
            "2026-07-02T02:30:00Z",
        ]
    )

    data_dir = tmp_path / "restore" / "data"
    assert exit_code == 0
    assert (data_dir / "PG_VERSION").read_text() == "15\n"
    assert (data_dir / "pg_wal" / "00000001000000000000000A").read_bytes() == b"wal"
    assert (
        tmp_path / "restore" / "wal" / "00000001000000000000000B"
    ).read_bytes() == b"archived-wal"
    assert (data_dir / "recovery.signal").exists()
    auto_conf = (data_dir / "postgresql.auto.conf").read_text()
    assert "restore_command" in auto_conf
    assert "cp /pitr-restore/wal/%f %p" in auto_conf
    assert "recovery_target_time = '2026-07-02T02:30:00+00:00'" in auto_conf
    assert (tmp_path / "restore" / "manifest.json").exists()


def test_prepare_refuses_non_empty_target_dir(monkeypatch, tmp_path):
    target = tmp_path / "restore"
    target.mkdir()
    (target / "existing").write_text("do not overwrite")
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda config: FakeClient({}))

    with pytest.raises(SystemExit, match="Target directory must be empty"):
        pitr_restore.main(["prepare", "--target-dir", str(target)])


def test_fetch_wal_downloads_expected_timeline_key(monkeypatch, tmp_path):
    wal_name = "00000001000000000000000A"
    key = f"postgres/pitr/mvn-api/wal/00000001/{wal_name}"
    client = FakeClient({key: b"wal-bytes"})
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda config: client)

    destination = tmp_path / "pg_wal" / wal_name
    exit_code = pitr_restore.main(
        ["fetch-wal", "--wal-name", wal_name, "--destination", str(destination)]
    )

    assert exit_code == 0
    assert destination.read_bytes() == b"wal-bytes"
    assert client.downloads[0][0] == key


def test_fetch_wal_rejects_invalid_wal_name(monkeypatch, tmp_path):
    monkeypatch.setattr(pitr_restore, "load_config", lambda: FakeConfig)
    monkeypatch.setattr(pitr_restore, "build_client", lambda config: FakeClient({}))

    with pytest.raises(SystemExit, match="Invalid WAL filename"):
        pitr_restore.main(
            ["fetch-wal", "--wal-name", "../../bad", "--destination", str(tmp_path / "bad")]
        )
