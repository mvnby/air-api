from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from core.config import settings
from models import AnalyticsConnection, DocumentDriveConnection, Storefront, Tenant
from services.analytics_connection_contracts import AnalyticsCredentialCipher
from services.document_drive_contracts import DocumentDriveCredentialCipher
from services.integration_credential_rotation_service import (
    IntegrationCredentialRotationService,
)
from services.integration_credential_rotation_token import (
    IntegrationCredentialRotationBlockedError,
)


_MASTER = "shared-integration-master-key-000000001"
_LEGACY = "legacy-node-auth-secret-at-least-32-bytes"


def _keyring(write_mode: str) -> str:
    return json.dumps(
        {
            "active_key_id": "integration-2026-09",
            "write_mode": write_mode,
            "keys": {"integration-2026-09": _MASTER},
            "legacy_secret_keys": [_LEGACY],
        }
    )


@pytest.fixture
async def rotation_session(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", _LEGACY)
    monkeypatch.setattr(
        settings,
        "INTEGRATION_CREDENTIAL_KEYRING_JSON",
        _keyring("legacy"),
    )
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'credential-rotation.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(Tenant(id=21, slug="vitebsk", display_name="Vitebsk"))
        session.add(
            Storefront(
                id=71,
                tenant_id=21,
                slug="main",
                display_name="Main",
                status="active",
                is_default=True,
            )
        )
        analytics_payload = {"oauth_token": "analytics-secret"}
        drive_payload = {"refresh_token": "drive-secret", "access_token": "access"}
        session.add_all(
            [
                AnalyticsConnection(
                    id=1,
                    tenant_id=21,
                    storefront_id=71,
                    provider="yandex_metrika",
                    status="active",
                    public_config={"counter_id": "123"},
                    encrypted_credentials=AnalyticsCredentialCipher.encrypt(
                        analytics_payload,
                        tenant_id=21,
                        storefront_id=71,
                        provider="yandex_metrika",
                    ),
                    credentials_fingerprint=AnalyticsCredentialCipher.fingerprint(
                        "analytics-secret"
                    ),
                ),
                DocumentDriveConnection(
                    id=2,
                    tenant_id=21,
                    provider="google_drive",
                    status="disabled",
                    encrypted_credentials=DocumentDriveCredentialCipher.encrypt(
                        drive_payload,
                        tenant_id=21,
                        provider="google_drive",
                    ),
                    credentials_fingerprint=DocumentDriveCredentialCipher.fingerprint(
                        drive_payload
                    ),
                    connection_key="connection-key",
                ),
            ]
        )
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_rotation_rewraps_all_rows_and_is_idempotent(
    rotation_session,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_CREDENTIAL_KEYRING_JSON",
        _keyring("active"),
    )

    async def allow_test_database(_session):
        return None

    monkeypatch.setattr(
        IntegrationCredentialRotationService,
        "_lock_primary_transaction",
        allow_test_database,
    )
    plan = await IntegrationCredentialRotationService.plan(rotation_session)
    assert plan["ready"] is True
    assert plan["complete"] is False
    assert plan["counts"] == {
        "active": 0,
        "retained": 0,
        "legacy": 2,
        "unreadable": 0,
        "fingerprint_drift": 0,
    }
    assert {row["status"] for row in plan["rows"]} == {"active", "disabled"}
    assert all("credentials" not in row for row in plan["rows"])

    result = await IntegrationCredentialRotationService.execute(
        rotation_session,
        plan_token=plan["plan_token"],
    )
    await rotation_session.commit()
    assert result["rewrapped"] == 2

    completed = await IntegrationCredentialRotationService.plan(rotation_session)
    assert completed["complete"] is True
    assert completed["counts"]["active"] == 2
    repeated = await IntegrationCredentialRotationService.execute(
        rotation_session,
        plan_token=completed["plan_token"],
    )
    await rotation_session.commit()
    assert repeated["rewrapped"] == 0
    assert repeated["unchanged"] == 2

    analytics = (
        await rotation_session.execute(select(AnalyticsConnection))
    ).scalar_one()
    drive = (
        await rotation_session.execute(select(DocumentDriveConnection))
    ).scalar_one()
    assert analytics.encrypted_credentials.startswith(
        "mvn-integrations-v1.integration-2026-09."
    )
    assert drive.encrypted_credentials.startswith(
        "mvn-integrations-v1.integration-2026-09."
    )


@pytest.mark.asyncio
async def test_execute_rejects_stale_reviewed_row_hash(
    rotation_session,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_CREDENTIAL_KEYRING_JSON",
        _keyring("active"),
    )

    async def allow_test_database(_session):
        return None

    monkeypatch.setattr(
        IntegrationCredentialRotationService,
        "_lock_primary_transaction",
        allow_test_database,
    )
    plan = await IntegrationCredentialRotationService.plan(rotation_session)
    row = (
        await rotation_session.execute(select(AnalyticsConnection))
    ).scalar_one()
    row.credentials_fingerprint = "state-changed-after-plan"
    rotation_session.add(row)
    await rotation_session.flush()

    with pytest.raises(IntegrationCredentialRotationBlockedError) as exc_info:
        await IntegrationCredentialRotationService.execute(
            rotation_session,
            plan_token=plan["plan_token"],
        )
    assert "state changed" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_plan_blocks_when_even_disabled_row_is_unreadable(
    rotation_session,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "INTEGRATION_CREDENTIAL_KEYRING_JSON",
        _keyring("active"),
    )
    row = (
        await rotation_session.execute(select(DocumentDriveConnection))
    ).scalar_one()
    row.encrypted_credentials = "not-a-valid-token"
    rotation_session.add(row)
    await rotation_session.flush()

    plan = await IntegrationCredentialRotationService.plan(rotation_session)
    assert plan["ready"] is False
    assert plan["counts"]["unreadable"] == 1
    assert plan["blockers"] == ["credentials_unreadable"]
    assert "plan_token" not in plan
