import asyncio

import pytest

from services.backup_run_runtime_service import BackupRunConflictError, BackupRunRuntimeService


@pytest.mark.asyncio
async def test_start_backup_blocks_parallel_jobs(monkeypatch):
    service = BackupRunRuntimeService()

    created_coroutines = []

    def _fake_create_task(coro):
        created_coroutines.append(coro)

        class _DummyTask:
            pass

        return _DummyTask()

    monkeypatch.setattr("services.backup_run_runtime_service.asyncio.create_task", _fake_create_task)

    first = await service.start_backup()
    assert first["status"] == "queued"

    with pytest.raises(BackupRunConflictError):
        await service.start_backup()

    for coro in created_coroutines:
        coro.close()


@pytest.mark.asyncio
async def test_backup_job_success(monkeypatch):
    service = BackupRunRuntimeService()

    monkeypatch.setattr(
        "services.backup_run_runtime_service.backup_service.perform_backup",
        lambda cleanup=True: True,
    )

    started = await service.start_backup()
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
