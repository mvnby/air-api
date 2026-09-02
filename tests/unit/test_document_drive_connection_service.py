from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import DocumentDriveConnection, Storefront, Tenant, TenantAuditEvent
from models.tenancy import TenantScope
from services.document_drive_connection_service import DocumentDriveConnectionService
from services.document_drive_contracts import (
    DocumentDriveConnectionError,
    DocumentDriveCredentialCipher,
    DocumentDriveFolder,
)


class _Adapter:
    def __init__(self, folder_id: str = "folder-21") -> None:
        self.folder_id = folder_id
        self.existing_folder_ids: list[str | None] = []

    async def account_label(self) -> str:
        return "owner@example.com"

    async def ensure_managed_folder(
        self,
        existing_folder_id: str | None,
    ) -> DocumentDriveFolder:
        self.existing_folder_ids.append(existing_folder_id)
        folder_id = existing_folder_id or self.folder_id
        return DocumentDriveFolder(
            id=folder_id,
            web_view_url=f"https://drive.google.com/drive/folders/{folder_id}",
        )


class _Provider:
    def __init__(self, adapter: _Adapter, *, refreshed: bool = False) -> None:
        self._adapter = adapter
        self._refreshed = refreshed

    async def access_token(self, credentials):
        if self._refreshed:
            credentials["access_token"] = "refreshed-access-token"
        return str(credentials["access_token"])

    def adapter(self, access_token_value: str, **_kwargs):
        assert access_token_value
        self._adapter.connection_id = _kwargs.get("connection_id", "pending")
        return self._adapter


@pytest.fixture
async def document_drive_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'document-drive.db'}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                Tenant(id=21, slug="vitebsk", display_name="Витебск"),
                Tenant(id=22, slug="polotsk", display_name="Полоцк"),
                Storefront(
                    id=71,
                    tenant_id=21,
                    slug="main",
                    display_name="Витебск",
                    status="active",
                    is_default=True,
                ),
                Storefront(
                    id=72,
                    tenant_id=22,
                    slug="main",
                    display_name="Полоцк",
                    status="active",
                    is_default=True,
                ),
            ]
        )
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_connection_is_encrypted_and_tenant_scoped(document_drive_session):
    secret = "refresh-token-must-not-be-plaintext"
    credentials = {
        "access_token": "temporary-access-token",
        "refresh_token": secret,
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/drive.file"],
    }
    adapter = _Adapter()
    scope = TenantScope(tenant_id=21, storefront_id=71)

    status = await DocumentDriveConnectionService.complete_authorization(
        document_drive_session,
        tenant_scope=scope,
        credentials=credentials,
        actor_staff_user_id=5,
        actor_username="owner",
        provider=_Provider(adapter),
    )

    assert status.connected is True
    assert status.account_label == "owner@example.com"
    stored = (
        await document_drive_session.execute(select(DocumentDriveConnection))
    ).scalar_one()
    assert stored.tenant_id == 21
    assert secret not in stored.encrypted_credentials
    assert DocumentDriveCredentialCipher.decrypt(
        stored.encrypted_credentials,
        tenant_id=21,
        provider="google_drive",
    ) == credentials
    with pytest.raises(DocumentDriveConnectionError) as moved_ciphertext:
        DocumentDriveCredentialCipher.decrypt(
            stored.encrypted_credentials,
            tenant_id=22,
            provider="google_drive",
        )
    assert moved_ciphertext.value.code == "credentials_unreadable"
    assert (
        await DocumentDriveConnectionService.status(
            document_drive_session,
            tenant_scope=TenantScope(tenant_id=22, storefront_id=72),
        )
    ).connected is False

    audit = (
        await document_drive_session.execute(select(TenantAuditEvent))
    ).scalar_one()
    assert audit.tenant_id == 21
    assert secret not in str(audit.change_set)


@pytest.mark.asyncio
async def test_reconnect_reuses_managed_folder(document_drive_session):
    scope = TenantScope(tenant_id=21, storefront_id=71)
    first_adapter = _Adapter("original-folder")
    credentials = {"access_token": "one", "refresh_token": "refresh-one"}
    await DocumentDriveConnectionService.complete_authorization(
        document_drive_session,
        tenant_scope=scope,
        credentials=credentials,
        actor_staff_user_id=5,
        actor_username="owner",
        provider=_Provider(first_adapter),
    )
    first_runtime = await DocumentDriveConnectionService.require_runtime(
        document_drive_session,
        tenant_scope=scope,
        provider=_Provider(_Adapter()),
    )

    second_adapter = _Adapter("must-not-be-used")
    await DocumentDriveConnectionService.complete_authorization(
        document_drive_session,
        tenant_scope=scope,
        credentials={"access_token": "two", "refresh_token": "refresh-two"},
        actor_staff_user_id=5,
        actor_username="owner",
        provider=_Provider(second_adapter),
    )

    assert second_adapter.existing_folder_ids == ["original-folder"]
    rows = (
        await document_drive_session.execute(select(DocumentDriveConnection))
    ).scalars().all()
    assert len(rows) == 1
    second_runtime = await DocumentDriveConnectionService.require_runtime(
        document_drive_session,
        tenant_scope=scope,
        provider=_Provider(_Adapter()),
    )
    assert first_runtime.adapter.connection_id != second_runtime.adapter.connection_id


@pytest.mark.asyncio
async def test_runtime_factory_fails_closed_and_persists_refresh(document_drive_session):
    missing_scope = TenantScope(tenant_id=22, storefront_id=72)
    with pytest.raises(DocumentDriveConnectionError) as exc_info:
        await DocumentDriveConnectionService.require_runtime(
            document_drive_session,
            tenant_scope=missing_scope,
            provider=_Provider(_Adapter()),
        )
    assert exc_info.value.code == "document_drive_not_connected"

    scope = TenantScope(tenant_id=21, storefront_id=71)
    await DocumentDriveConnectionService.complete_authorization(
        document_drive_session,
        tenant_scope=scope,
        credentials={"access_token": "old", "refresh_token": "refresh"},
        actor_staff_user_id=5,
        actor_username="owner",
        provider=_Provider(_Adapter()),
    )
    runtime_before_refresh = await DocumentDriveConnectionService.require_runtime(
        document_drive_session,
        tenant_scope=scope,
        provider=_Provider(_Adapter()),
    )
    runtime = await DocumentDriveConnectionService.require_runtime(
        document_drive_session,
        tenant_scope=scope,
        provider=_Provider(_Adapter(), refreshed=True),
    )
    assert runtime.managed_folder_id == "folder-21"
    assert runtime.adapter.connection_id == runtime_before_refresh.adapter.connection_id
    stored = (
        await document_drive_session.execute(select(DocumentDriveConnection))
    ).scalar_one()
    assert DocumentDriveCredentialCipher.decrypt(
        stored.encrypted_credentials,
        tenant_id=21,
        provider="google_drive",
    )[
        "access_token"
    ] == "refreshed-access-token"
    assert stored.last_verified_at is not None


@pytest.mark.asyncio
async def test_runtime_records_revoked_google_access(document_drive_session):
    class _RevokedProvider(_Provider):
        async def access_token(self, credentials):
            del credentials
            raise DocumentDriveConnectionError(
                "google_drive_access_denied",
                "Доступ отозван",
            )

    scope = TenantScope(tenant_id=21, storefront_id=71)
    await DocumentDriveConnectionService.complete_authorization(
        document_drive_session,
        tenant_scope=scope,
        credentials={"access_token": "old", "refresh_token": "refresh"},
        actor_staff_user_id=5,
        actor_username="owner",
        provider=_Provider(_Adapter()),
    )

    with pytest.raises(DocumentDriveConnectionError):
        await DocumentDriveConnectionService.require_runtime(
            document_drive_session,
            tenant_scope=scope,
            provider=_RevokedProvider(_Adapter()),
        )

    status = await DocumentDriveConnectionService.status(
        document_drive_session,
        tenant_scope=scope,
    )
    assert status.connected is False
    assert status.last_error_code == "google_drive_access_denied"
