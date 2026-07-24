import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.google_vision_runtime import (
    verify_google_vision_credentials_startup,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_COMPOSE_FILES = (
    "docker-compose.prod.yml",
    "deploy/ha/mvn-api/docker-compose.primary.yml",
    "deploy/ha/mvn-api/docker-compose.standby.yml",
    "deploy/ha/mvn-api/docker-compose.patroni.yml",
    "deploy/ha/zakup/docker-compose.primary.yml",
    "deploy/ha/zakup/docker-compose.standby.yml",
    "deploy/ha/zakup/docker-compose.patroni.yml",
)


def _settings(path: str, *, production: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        is_production=production,
        GOOGLE_VISION_CREDENTIALS_FILE=path,
    )


def _service_account_payload() -> dict[str, str]:
    return {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key",
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\n"
            "not-a-real-private-key\n"
            "-----END PRIVATE KEY-----\n"
        ),
        "client_email": "vision@test-project.iam.gserviceaccount.com",
        "client_id": "123",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://example.invalid/cert",
    }


def test_all_production_composes_pin_google_vision_container_path():
    for relative_path in PRODUCTION_COMPOSE_FILES:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert (
            "GOOGLE_VISION_CREDENTIALS_FILE: /app/g-vision-ocr.json"
            in text
        ), relative_path
        assert "/app/g-vision-ocr.json:ro" in text, relative_path


def test_startup_rejects_missing_or_non_file_credentials(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(RuntimeError, match="not readable"):
        verify_google_vision_credentials_startup(_settings(str(missing)))

    directory = tmp_path / "credentials"
    directory.mkdir()
    with pytest.raises(RuntimeError, match="not readable"):
        verify_google_vision_credentials_startup(_settings(str(directory)))


def test_startup_rejects_invalid_service_account_json(tmp_path):
    credentials = tmp_path / "vision.json"
    credentials.write_text(json.dumps(_service_account_payload()), encoding="utf-8")

    with pytest.raises(RuntimeError, match="startup validation failed"):
        verify_google_vision_credentials_startup(_settings(str(credentials)))


def test_startup_accepts_readable_service_account_file(tmp_path, monkeypatch):
    credentials = tmp_path / "vision.json"
    credentials.write_text("{}", encoding="utf-8")
    loaded = []

    monkeypatch.setattr(
        "services.google_vision_runtime.service_account.Credentials"
        ".from_service_account_file",
        lambda path, *, scopes: loaded.append((Path(path), scopes)),
    )

    verify_google_vision_credentials_startup(_settings(str(credentials)))

    assert loaded == [
        (
            credentials,
            ["https://www.googleapis.com/auth/cloud-vision"],
        )
    ]


def test_startup_skips_unconfigured_or_non_production_credentials(tmp_path):
    verify_google_vision_credentials_startup(_settings(""))
    verify_google_vision_credentials_startup(
        _settings(str(tmp_path / "missing.json"), production=False)
    )


@pytest.mark.asyncio
async def test_app_lifespan_checks_vision_before_other_startup(monkeypatch):
    from core import app_lifespan as lifespan_module

    events = []

    monkeypatch.setattr(
        lifespan_module,
        "_verify_google_vision_credentials",
        lambda: events.append("vision"),
    )

    async def verify_storage():
        events.append("storage")

    async def bootstrap_database():
        events.append("database")
        return False

    async def stop_scheduler(_app):
        return None

    monkeypatch.setattr(
        lifespan_module,
        "_verify_private_attachment_storage",
        verify_storage,
    )
    monkeypatch.setattr(
        lifespan_module,
        "_bootstrap_database",
        bootstrap_database,
    )
    monkeypatch.setattr(
        lifespan_module,
        "_start_scheduler_supervisor",
        lambda _app: False,
    )
    monkeypatch.setattr(
        lifespan_module,
        "_stop_scheduler_supervisor",
        stop_scheduler,
    )

    app = SimpleNamespace(state=SimpleNamespace())
    async with lifespan_module.app_lifespan(app):
        assert events == ["vision", "storage", "database"]
