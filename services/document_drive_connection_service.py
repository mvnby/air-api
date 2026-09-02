from __future__ import annotations

from datetime import datetime, timezone
import secrets
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.request_context import current_request_id
from models import DocumentDriveConnection, TenantAuditEvent
from models.tenancy import TenantScope
from schemas_document_drive import DocumentDriveStatusResponse
from services.document_drive_contracts import (
    DocumentDriveConnectionError,
    DocumentDriveCredentialCipher,
    DocumentDriveRuntime,
)
from services.document_drive_provider import (
    DocumentDriveProviderFactory,
    get_document_drive_provider,
)


GOOGLE_DRIVE_PROVIDER = "google_drive"


class DocumentDriveConnectionService:
    @staticmethod
    async def _get_connection(
        session: AsyncSession,
        *,
        tenant_id: int,
        for_update: bool = False,
    ) -> DocumentDriveConnection | None:
        statement = select(DocumentDriveConnection).where(
            DocumentDriveConnection.tenant_id == tenant_id,
            DocumentDriveConnection.provider == GOOGLE_DRIVE_PROVIDER,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    @classmethod
    async def status(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> DocumentDriveStatusResponse:
        connection = await cls._get_connection(
            session,
            tenant_id=tenant_scope.tenant_id,
        )
        connected = bool(connection and connection.status == "active")
        last_error_code = connection.last_error_code if connection else None
        if last_error_code == "google_drive_access_denied":
            connected = False
        if connected:
            try:
                DocumentDriveCredentialCipher.decrypt(
                    connection.encrypted_credentials,
                    tenant_id=connection.tenant_id,
                    provider=connection.provider,
                )
            except DocumentDriveConnectionError as exc:
                connected = False
                last_error_code = exc.code
        return DocumentDriveStatusResponse(
            connected=connected,
            account_label=connection.account_label if connection else None,
            managed_folder_url=connection.managed_folder_url if connection else None,
            connected_at=connection.connected_at if connection else None,
            last_verified_at=connection.last_verified_at if connection else None,
            last_error_code=last_error_code,
        )

    @classmethod
    async def complete_authorization(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        credentials: dict[str, Any],
        actor_staff_user_id: int | None,
        actor_username: str,
        provider: DocumentDriveProviderFactory | None = None,
    ) -> DocumentDriveStatusResponse:
        active_provider = provider or get_document_drive_provider()
        connection = await cls._get_connection(
            session,
            tenant_id=tenant_scope.tenant_id,
            for_update=True,
        )
        access_token_value = await active_provider.access_token(credentials)
        adapter = active_provider.adapter(access_token_value)
        previous_folder_id = connection.managed_folder_id if connection else None
        folder = await adapter.ensure_managed_folder(
            previous_folder_id
        )
        account_label = await adapter.account_label()
        now = datetime.now(timezone.utc)
        is_new = connection is None
        if connection is None:
            connection = DocumentDriveConnection(
                tenant_id=tenant_scope.tenant_id,
                encrypted_credentials="",
                credentials_fingerprint="",
                connection_key="",
            )
        connection.status = "active"
        connection.encrypted_credentials = DocumentDriveCredentialCipher.encrypt(
            credentials,
            tenant_id=tenant_scope.tenant_id,
            provider=GOOGLE_DRIVE_PROVIDER,
        )
        connection.credentials_fingerprint = DocumentDriveCredentialCipher.fingerprint(
            credentials
        )
        # Rotate only on an explicit OAuth completion. Ordinary access-token
        # refreshes keep this identity stable, while a reconnected account
        # invalidates edit sessions tied to the previous credential.
        connection.connection_key = secrets.token_hex(16)
        connection.account_label = account_label
        connection.managed_folder_id = folder.id
        connection.managed_folder_url = folder.web_view_url
        connection.last_verified_at = now
        connection.last_error_code = None
        connection.updated_at = now
        if is_new:
            connection.connected_at = now
        session.add(connection)
        await session.flush()
        session.add(
            TenantAuditEvent(
                tenant_id=tenant_scope.tenant_id,
                storefront_id=tenant_scope.storefront_id,
                actor_staff_user_id=actor_staff_user_id,
                actor_username=actor_username,
                action=(
                    "document_drive_connection.created"
                    if is_new
                    else "document_drive_connection.updated"
                ),
                entity_type="document_drive_connection",
                entity_id=int(connection.id or 0),
                request_id=current_request_id(),
                change_set={
                    "provider": GOOGLE_DRIVE_PROVIDER,
                    "credential_replaced": True,
                    "managed_folder_reused": bool(
                        previous_folder_id and previous_folder_id == folder.id
                    ),
                },
            )
        )
        await session.commit()
        return await cls.status(session, tenant_scope=tenant_scope)

    @classmethod
    async def require_runtime(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        provider: DocumentDriveProviderFactory | None = None,
    ) -> DocumentDriveRuntime:
        """Build a tenant-bound Drive adapter or fail closed when disconnected."""

        connection = await cls._get_connection(
            session,
            tenant_id=tenant_scope.tenant_id,
            for_update=True,
        )
        if (
            connection is None
            or connection.status != "active"
            or not connection.managed_folder_id
        ):
            raise DocumentDriveConnectionError(
                "document_drive_not_connected",
                "Подключите Google Диск в настройках документов",
                status_code=409,
            )
        credentials = DocumentDriveCredentialCipher.decrypt(
            connection.encrypted_credentials,
            tenant_id=connection.tenant_id,
            provider=connection.provider,
        )
        fingerprint_before = DocumentDriveCredentialCipher.fingerprint(credentials)
        active_provider = provider or get_document_drive_provider()
        try:
            access_token_value = await active_provider.access_token(credentials)
        except DocumentDriveConnectionError as exc:
            connection.last_error_code = exc.code
            connection.updated_at = datetime.now(timezone.utc)
            session.add(connection)
            await session.commit()
            raise
        fingerprint_after = DocumentDriveCredentialCipher.fingerprint(credentials)
        if fingerprint_after != fingerprint_before:
            connection.encrypted_credentials = DocumentDriveCredentialCipher.encrypt(
                credentials,
                tenant_id=connection.tenant_id,
                provider=connection.provider,
            )
            connection.credentials_fingerprint = fingerprint_after
            connection.updated_at = datetime.now(timezone.utc)
        connection.last_verified_at = datetime.now(timezone.utc)
        connection.last_error_code = None
        session.add(connection)
        await session.commit()
        return DocumentDriveRuntime(
            adapter=active_provider.adapter(
                access_token_value,
                connection_id=f"{connection.id}:{connection.connection_key}",
                managed_folder_id=connection.managed_folder_id,
            ),
            managed_folder_id=connection.managed_folder_id,
        )
