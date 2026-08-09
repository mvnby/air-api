import io
import os
import tarfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from services import backup_service
from services.backup_service import BackupConfigurationError, BackupService
from services.google_oauth_credentials import GoogleTokenRefreshError


def test_concurrent_initialization_creates_backup_directory_once(monkeypatch, tmp_path: Path):
    backup_dir = tmp_path / "backups"
    workers = 8
    barrier = threading.Barrier(workers)
    real_makedirs = os.makedirs

    def synchronized_makedirs(path, mode=0o777, exist_ok=False):
        barrier.wait(timeout=5)
        return real_makedirs(path, mode=mode, exist_ok=exist_ok)

    monkeypatch.setattr(backup_service, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(backup_service.os, "makedirs", synchronized_makedirs)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        services = list(executor.map(lambda _: BackupService(), range(workers)))

    assert len(services) == workers
    assert backup_dir.is_dir()


def test_list_backups_classifies_and_sorts(monkeypatch):
    service = BackupService()
    service.backup_folder_id = "folder-id"

    class _FakeGoogleService:
        def list_files(self, folder_id: str, limit: int = 20):
            assert folder_id == "folder-id"
            assert limit == 10
            return [
                {
                    "id": "media1",
                    "name": "media_backup_20260101_000000.tar.gz",
                    "createdTime": "2026-01-01T00:00:00Z",
                    "mimeType": "application/gzip",
                    "size": "1024",
                },
                {
                    "id": "db2",
                    "name": "backup_air_conditioners_20260102_120000.sql.gz",
                    "createdTime": "2026-01-02T12:00:00Z",
                    "mimeType": "application/gzip",
                    "size": "2048",
                },
                {
                    "id": "ignored",
                    "name": "notes.txt",
                    "createdTime": "2026-01-03T00:00:00Z",
                    "mimeType": "text/plain",
                    "size": "128",
                },
            ]

    monkeypatch.setattr("services.backup_service.get_google_service", lambda: _FakeGoogleService())

    items = service.list_backups(limit=10)

    assert len(items) == 2
    assert items[0]["id"] == "db2"
    assert items[0]["kind"] == "db"
    assert items[0]["size_bytes"] == 2048
    assert items[1]["id"] == "media1"
    assert items[1]["kind"] == "media"
    assert items[1]["size_bytes"] == 1024
    assert items[0]["created_at"] > items[1]["created_at"]


def test_list_backups_propagates_google_auth_failure(monkeypatch):
    service = BackupService()
    service.backup_folder_id = "folder-id"

    class _FailingGoogleService:
        def list_files(self, _folder_id: str, limit: int = 20):
            raise GoogleTokenRefreshError("Google OAuth token refresh failed")

    monkeypatch.setattr(
        "services.backup_service.get_google_service",
        lambda: _FailingGoogleService(),
    )

    with pytest.raises(GoogleTokenRefreshError, match="token refresh failed"):
        service.list_backups(limit=100)


def test_list_backups_fails_closed_without_backup_folder_id():
    service = BackupService()
    service.backup_folder_id = None

    with pytest.raises(BackupConfigurationError, match="BACKUP_FOLDER_ID"):
        service.list_backups(limit=100)


def test_production_backup_fails_before_dump_without_backup_folder_id(monkeypatch):
    service = BackupService()
    service.backup_folder_id = None
    monkeypatch.setattr(
        "services.backup_service.settings",
        type(
            "ProductionSettings",
            (),
            {"is_production": True, "ENVIRONMENT": "production"},
        )(),
    )
    monkeypatch.setattr(
        service,
        "create_dump",
        lambda: pytest.fail("dump must not start without a destination folder"),
    )

    with pytest.raises(BackupConfigurationError, match="BACKUP_FOLDER_ID"):
        service.perform_backup()


def test_sanitize_plain_sql_dump_removes_client_only_settings(tmp_path: Path):
    dump_path = tmp_path / "backup.sql"
    dump_path.write_text(
        "\n".join(
            [
                "SET statement_timeout = 0;",
                "SET transaction_timeout = 0;",
                "CREATE TABLE product (id integer);",
                "",
            ]
        ),
        encoding="utf-8",
    )

    changed = BackupService.sanitize_plain_sql_dump(str(dump_path))

    assert changed is True
    sanitized = dump_path.read_text(encoding="utf-8")
    assert "SET statement_timeout = 0;" in sanitized
    assert "SET transaction_timeout = 0;" not in sanitized
    assert "CREATE TABLE product" in sanitized


@pytest.mark.asyncio
async def test_restore_from_file_async_uses_psql(monkeypatch):
    service = BackupService()
    captured = {}

    class _Proc:
        returncode = 0

        async def communicate(self):
            return b"ok", b""

    async def _fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _Proc()

    monkeypatch.setattr("services.backup_service.asyncio.create_subprocess_exec", _fake_exec)
    await service.restore_from_file_async("/tmp/test_restore.sql")

    assert captured["args"][0] == "psql"
    assert "-f" in captured["args"]
    assert "/tmp/test_restore.sql" in captured["args"]
    assert "--no-psqlrc" in captured["args"]
    assert "--set=ON_ERROR_STOP=1" in captured["args"]
    assert "--single-transaction" in captured["args"]
    assert captured["kwargs"]["env"]["PGPASSWORD"] == service.db_password


@pytest.mark.asyncio
async def test_restore_from_file_async_raises_on_psql_error(monkeypatch):
    service = BackupService()

    class _Proc:
        returncode = 1

        async def communicate(self):
            return b"", b"fatal: restore failed"

    async def _fake_exec(*args, **kwargs):
        return _Proc()

    monkeypatch.setattr("services.backup_service.asyncio.create_subprocess_exec", _fake_exec)

    with pytest.raises(Exception, match="Database restore failed"):
        await service.restore_from_file_async("/tmp/broken_restore.sql")


def test_restore_media_from_archive_restores_media_dir(monkeypatch, tmp_path: Path):
    service = BackupService()
    service.media_dir = str(tmp_path / "media")

    media_dir = Path(service.media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "old.txt").write_text("old", encoding="utf-8")

    source_root = tmp_path / "src"
    source_media = source_root / "media"
    source_media.mkdir(parents=True, exist_ok=True)
    (source_media / "new.txt").write_text("new", encoding="utf-8")

    archive_path = tmp_path / "media_backup_test.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(source_media, arcname="media")

    monkeypatch.setattr(service, "create_media_archive", lambda: str(tmp_path / "safety_media.tar.gz"))

    safety_path = service.restore_media_from_archive(str(archive_path))
    assert safety_path.endswith("safety_media.tar.gz")
    assert (media_dir / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (media_dir / "old.txt").exists()


def test_safe_extract_tar_rejects_special_files(tmp_path: Path):
    archive_path = tmp_path / "unsafe.tar"
    with tarfile.open(archive_path, "w") as tar:
        fifo = tarfile.TarInfo("media/pipe")
        fifo.type = tarfile.FIFOTYPE
        tar.addfile(fifo)

    destination = tmp_path / "destination"
    destination.mkdir()

    with pytest.raises(Exception, match="special file"):
        BackupService._safe_extract_tar(str(archive_path), str(destination))


def test_safe_extract_tar_rejects_uncompressed_size_limit(monkeypatch, tmp_path: Path):
    archive_path = tmp_path / "oversized.tar"
    with tarfile.open(archive_path, "w") as tar:
        content = b"too-large"
        item = tarfile.TarInfo("media/file.bin")
        item.size = len(content)
        tar.addfile(item, io.BytesIO(content))

    monkeypatch.setattr(BackupService, "_MAX_MEDIA_ARCHIVE_UNCOMPRESSED_BYTES", 1)
    destination = tmp_path / "destination"
    destination.mkdir()

    with pytest.raises(Exception, match="uncompressed size"):
        BackupService._safe_extract_tar(str(archive_path), str(destination))
