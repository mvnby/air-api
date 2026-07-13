import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.security import get_current_owner_username
from routers.manager_backups import router as manager_backups_router
from services.backup_service import BackupConfigurationError
from services.google_oauth_credentials import GoogleTokenRefreshError


@pytest.fixture()
async def backups_client():
    app = FastAPI()
    app.include_router(manager_backups_router)
    app.dependency_overrides[get_current_owner_username] = lambda: "admin"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_list_backups_maps_google_auth_failure_to_redacted_502(
    backups_client,
    monkeypatch,
):
    def _fail_list(*, limit: int):
        assert limit == 100
        raise GoogleTokenRefreshError("provider-secret-detail")

    monkeypatch.setattr("routers.manager_backups.backup_service.list_backups", _fail_list)

    response = await backups_client.get("/api/manager/backups")

    assert response.status_code == 502
    payload = response.json()
    assert payload["detail"]["error_code"] == "backup_list_unavailable"
    assert "provider-secret-detail" not in response.text


@pytest.mark.asyncio
async def test_list_backups_maps_missing_storage_configuration_to_redacted_503(
    backups_client,
    monkeypatch,
):
    def _fail_list(*, limit: int):
        assert limit == 100
        raise BackupConfigurationError("BACKUP_FOLDER_ID=private-provider-detail")

    monkeypatch.setattr("routers.manager_backups.backup_service.list_backups", _fail_list)

    response = await backups_client.get("/api/manager/backups")

    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["error_code"] == "backup_list_unavailable"
    assert "private-provider-detail" not in response.text


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
    monkeypatch.setattr("routers.manager_backups.settings.BACKUP_RESTORE_ENABLED", True)

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
    monkeypatch.setattr("routers.manager_backups.settings.BACKUP_RESTORE_ENABLED", True)
    monkeypatch.setattr("routers.manager_backups.backup_run_runtime_service.has_active_job", lambda: True)

    response = await backups_client.post("/api/manager/backups/restore/db-file-1")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_start_restore_is_disabled_by_default(backups_client, monkeypatch):
    monkeypatch.setattr("routers.manager_backups.settings.BACKUP_RESTORE_ENABLED", False)

    async def _unexpected_restore(file_id: str):
        raise AssertionError(f"restore must stay disabled: {file_id}")

    monkeypatch.setattr(
        "routers.manager_backups.backup_restore_runtime_service.start_restore",
        _unexpected_restore,
    )

    response = await backups_client.post("/api/manager/backups/restore/db-file-1")
    assert response.status_code == 503
    assert "disabled" in response.json()["detail"].lower()
