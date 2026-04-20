import pytest

from services.backup_service import BackupService


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
