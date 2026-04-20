import asyncio
import gzip
from pathlib import Path

import pytest

from services.backup_restore_runtime_service import BackupRestoreRuntimeService, RestoreConflictError


@pytest.mark.asyncio
async def test_start_restore_blocks_parallel_jobs(monkeypatch):
    service = BackupRestoreRuntimeService()

    monkeypatch.setattr(
        "services.backup_restore_runtime_service.backup_service.list_backups",
        lambda limit=200: [
            {
                "id": "db-1",
                "name": "backup_air_conditioners_20260101_000000.sql",
                "kind": "db",
            }
        ],
    )

    created_coroutines = []

    def _fake_create_task(coro):
        created_coroutines.append(coro)

        class _DummyTask:
            pass

        return _DummyTask()

    monkeypatch.setattr("services.backup_restore_runtime_service.asyncio.create_task", _fake_create_task)

    first = await service.start_restore("db-1")
    assert first["status"] == "queued"

    with pytest.raises(RestoreConflictError):
        await service.start_restore("db-1")

    for coro in created_coroutines:
        coro.close()


@pytest.mark.asyncio
async def test_restore_job_handles_gzip_pipeline(monkeypatch, tmp_path: Path):
    service = BackupRestoreRuntimeService()
    called = {"decompress": 0, "restore_path": None}

    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("services.backup_restore_runtime_service.BACKUP_DIR", str(tmp_path))

    monkeypatch.setattr(
        "services.backup_restore_runtime_service.backup_service.list_backups",
        lambda limit=200: [
            {
                "id": "db-gz",
                "name": "backup_air_conditioners_20260101_000000.sql.gz",
                "kind": "db",
            }
        ],
    )
    monkeypatch.setattr(
        "services.backup_restore_runtime_service.backup_service.create_dump",
        lambda prefix=None: str(tmp_path / "safety_pre_restore.sql"),
    )

    def _fake_download(file_id: str, destination_path: str):
        with gzip.open(destination_path, "wb") as out:
            out.write(b"select 1;")
        return destination_path

    monkeypatch.setattr(
        "services.backup_restore_runtime_service.backup_service.download_backup_file",
        _fake_download,
    )

    def _fake_decompress(source_path: str, destination_path: str):
        called["decompress"] += 1
        with gzip.open(source_path, "rb") as src, open(destination_path, "wb") as dst:
            dst.write(src.read())
        return destination_path

    monkeypatch.setattr(
        "services.backup_restore_runtime_service.backup_service.decompress_gzip_file",
        _fake_decompress,
    )

    async def _fake_restore(sql_path: str):
        called["restore_path"] = sql_path
        assert sql_path.endswith(".sql")
        assert Path(sql_path).exists()

    monkeypatch.setattr(
        "services.backup_restore_runtime_service.backup_service.restore_from_file_async",
        _fake_restore,
    )

    started = await service.start_restore("db-gz")
    job_id = started["job_id"]

    final_job = None
    for _ in range(100):
        current = service.get_job(job_id)
        assert current is not None
        if current["status"] in {"success", "failed"}:
            final_job = current
            break
        await asyncio.sleep(0.01)

    assert final_job is not None
    assert final_job["status"] == "success"
    assert called["decompress"] == 1
    assert called["restore_path"] is not None
