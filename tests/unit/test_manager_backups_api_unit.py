import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.security import get_current_username
from routers.manager_backups import router as manager_backups_router


@pytest.fixture()
async def backups_client():
    app = FastAPI()
    app.include_router(manager_backups_router)
    app.dependency_overrides[get_current_username] = lambda: "admin"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_start_manual_backup_requires_production(backups_client, monkeypatch):
    class _Settings:
        is_production = False
        ENVIRONMENT = "local"

    monkeypatch.setattr("routers.manager_backups.settings", _Settings())

    response = await backups_client.post("/api/manager/backups/run")
    assert response.status_code == 400
    assert "enabled only in production" in response.json()["detail"]


@pytest.mark.asyncio
async def test_start_manual_backup_rejects_when_restore_running(backups_client, monkeypatch):
    class _Settings:
        is_production = True
        ENVIRONMENT = "production"

    monkeypatch.setattr("routers.manager_backups.settings", _Settings())
    monkeypatch.setattr("routers.manager_backups.backup_restore_runtime_service.has_active_job", lambda: True)

    response = await backups_client.post("/api/manager/backups/run")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_start_manual_backup_returns_job(backups_client, monkeypatch):
    class _Settings:
        is_production = True
        ENVIRONMENT = "production"

    monkeypatch.setattr("routers.manager_backups.settings", _Settings())
    async def _fake_start_backup():
        return {
            "job_id": "job-1",
            "status": "queued",
            "stage": "queued",
        }

    monkeypatch.setattr("routers.manager_backups.backup_run_runtime_service.start_backup", _fake_start_backup)

    response = await backups_client.post("/api/manager/backups/run")
    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["status"] == "queued"


@pytest.mark.asyncio
async def test_get_manual_backup_status(backups_client, monkeypatch):
    monkeypatch.setattr(
        "routers.manager_backups.backup_run_runtime_service.get_job",
        lambda job_id: {
            "job_id": job_id,
            "status": "running",
            "stage": "running_backup",
            "error": None,
            "started_at": None,
            "finished_at": None,
        },
    )

    response = await backups_client.get("/api/manager/backups/run/job-2")
    assert response.status_code == 200
    assert response.json()["job_id"] == "job-2"


@pytest.mark.asyncio
async def test_start_restore_accepts_media_backup(backups_client, monkeypatch):
    async def _fake_start_restore(file_id: str):
        assert file_id == "media-file-1"
        return {
            "job_id": "restore-media-1",
            "status": "queued",
            "stage": "queued",
        }

    monkeypatch.setattr("routers.manager_backups.backup_restore_runtime_service.start_restore", _fake_start_restore)

    response = await backups_client.post("/api/manager/backups/restore/media-file-1")
    assert response.status_code == 202
    assert response.json()["job_id"] == "restore-media-1"


@pytest.mark.asyncio
async def test_start_restore_rejects_when_backup_running(backups_client, monkeypatch):
    monkeypatch.setattr("routers.manager_backups.backup_run_runtime_service.has_active_job", lambda: True)

    response = await backups_client.post("/api/manager/backups/restore/db-file-1")
    assert response.status_code == 409
