from datetime import datetime

import pytest

from core.config import settings
from services.backup_restore_runtime_service import RestoreConflictError


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_backups_requires_auth(async_client):
    resp = await async_client.get("/api/manager/backups")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_manager_backups_list(async_client, monkeypatch):
    headers = await _auth_headers(async_client)

    monkeypatch.setattr(
        "routers.manager_backups.backup_service.list_backups",
        lambda limit=100: [
            {
                "id": "db-1",
                "name": "backup_air_conditioners_20260101_000000.sql",
                "kind": "db",
                "created_at": datetime(2026, 1, 1, 0, 0, 0),
                "size_bytes": 1024,
                "mime_type": "application/sql",
            }
        ],
    )

    resp = await async_client.get("/api/manager/backups", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["kind"] == "db"


@pytest.mark.asyncio
async def test_manager_backups_restore_start_and_status(async_client, monkeypatch):
    headers = await _auth_headers(async_client)
    monkeypatch.setattr("routers.manager_backups.settings.BACKUP_RESTORE_ENABLED", True)

    async def _fake_start_restore(file_id: str):
        assert file_id == "db-restore-1"
        return {
            "job_id": "job-1",
            "status": "queued",
            "stage": "queued",
            "file_id": "db-restore-1",
            "file_name": "backup_air_conditioners_20260101_000000.sql",
            "kind": "db",
        }

    monkeypatch.setattr(
        "routers.manager_backups.backup_restore_runtime_service.start_restore",
        _fake_start_restore,
    )
    monkeypatch.setattr(
        "routers.manager_backups.backup_restore_runtime_service.get_job",
        lambda job_id: {
            "job_id": job_id,
            "file_id": "db-restore-1",
            "file_name": "backup_air_conditioners_20260101_000000.sql",
            "kind": "db",
            "status": "running",
            "stage": "restoring_database",
            "error": None,
            "started_at": datetime(2026, 1, 1, 0, 0, 0),
            "finished_at": None,
            "safety_dump_path": "backups/safety_pre_restore.sql",
        },
    )

    start_resp = await async_client.post("/api/manager/backups/restore/db-restore-1", headers=headers)
    assert start_resp.status_code == 202
    assert start_resp.json()["job_id"] == "job-1"

    status_resp = await async_client.get("/api/manager/backups/restore/job-1", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_manager_backups_restore_conflict(async_client, monkeypatch):
    headers = await _auth_headers(async_client)
    monkeypatch.setattr("routers.manager_backups.settings.BACKUP_RESTORE_ENABLED", True)

    async def _raise_conflict(_file_id: str):
        raise RestoreConflictError("Another restore job is already running")

    monkeypatch.setattr(
        "routers.manager_backups.backup_restore_runtime_service.start_restore",
        _raise_conflict,
    )

    start_resp = await async_client.post("/api/manager/backups/restore/db-restore-1", headers=headers)
    assert start_resp.status_code == 409
