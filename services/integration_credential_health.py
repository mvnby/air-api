"""Read-only runtime proof that persisted integrations are usable by this node."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import AnalyticsConnection
from models.document_drive_connection import DocumentDriveConnection
from models.platform_ai_connection import PlatformAIConnection
from services.platform_ai_connection_service import PlatformAICredentialCipher
from services.zaprosu_provider_service import ZaprosuError
from services.analytics_connection_contracts import AnalyticsConnectionError, AnalyticsCredentialCipher
from services.document_drive_contracts import DocumentDriveConnectionError, DocumentDriveCredentialCipher


async def integration_credential_health(session: AsyncSession) -> dict:
    checked = 0
    unreadable = 0
    for model in (AnalyticsConnection, DocumentDriveConnection, PlatformAIConnection):
        rows = (await session.execute(select(model))).scalars().all()
        for row in rows:
            checked += 1
            try:
                if isinstance(row, AnalyticsConnection):
                    AnalyticsCredentialCipher.decrypt(
                        row.encrypted_credentials,
                        tenant_id=row.tenant_id, storefront_id=row.storefront_id, provider=row.provider,
                    )
                elif isinstance(row, DocumentDriveConnection):
                    DocumentDriveCredentialCipher.decrypt(
                        row.encrypted_credentials, tenant_id=row.tenant_id, provider=row.provider,
                    )
                else:
                    PlatformAICredentialCipher.decrypt_with_source(row.encrypted_credentials)
            except (AnalyticsConnectionError, DocumentDriveConnectionError, ZaprosuError):
                unreadable += 1
    return {
        "status": "passed" if unreadable == 0 else "failed",
        "checked": checked,
        "unreadable": unreadable,
    }
