"""Personal OAuth credentials never confer access to another staff member's calls."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from models import StaffUser, Storefront, Tenant, TenantMembership
from models.call_recording import CallDriveConnection
from schemas_call_recordings import CallDriveStatus, CallFolderPayload
from services.call_drive_provider import CallDriveError, get_call_drive_provider
from services.document_drive_contracts import DocumentDriveCredentialCipher, DocumentDriveConnectionError


class CallDriveCredentialCipher(DocumentDriveCredentialCipher):
    _ENCRYPTION_CONTEXT = b"mvn.personal-call-drive.credentials.v1"
    _FINGERPRINT_CONTEXT = b"mvn.personal-call-drive.fingerprint.v1"


async def require_live_call_actor(session: AsyncSession, actor: CommandActor, *, write: bool = False) -> StaffUser:
    user = await session.get(StaffUser, actor.staff_user_id, populate_existing=True)
    membership = await session.scalar(select(TenantMembership).where(TenantMembership.staff_user_id == actor.staff_user_id, TenantMembership.tenant_id == actor.tenant_scope.tenant_id, TenantMembership.status == "active"))
    tenant = await session.get(Tenant, actor.tenant_scope.tenant_id, populate_existing=True)
    storefront = await session.get(Storefront, actor.tenant_scope.storefront_id, populate_existing=True)
    if (user is None or user.status != "active" or user.must_change_password or membership is None or membership.role not in {"owner", "admin", "manager"} or tenant is None or tenant.status != "active" or storefront is None or storefront.status != "active" or storefront.tenant_id != actor.tenant_scope.tenant_id):
        raise PermissionError("Доступ сотрудника к записям отозван")
    if write and (actor.tenant_scope.demo_read_only or tenant.demo_read_only):
        raise PermissionError("Демонстрационный доступ только для чтения")
    return user


class CallDriveConnectionService:
    @staticmethod
    def cipher_provider(row: CallDriveConnection) -> str:
        return f"call-drive:{row.staff_user_id}:{row.storefront_id}"

    @staticmethod
    async def get(session, actor, *, for_update=False, create=False):
        await require_live_call_actor(session, actor, write=create)
        statement = select(CallDriveConnection).where(CallDriveConnection.tenant_id == actor.tenant_scope.tenant_id, CallDriveConnection.storefront_id == actor.tenant_scope.storefront_id, CallDriveConnection.staff_user_id == actor.staff_user_id).execution_options(populate_existing=True)
        if for_update:
            statement = statement.with_for_update()
        row = await session.scalar(statement)
        if row is None and create:
            row = CallDriveConnection(tenant_id=actor.tenant_scope.tenant_id, storefront_id=actor.tenant_scope.storefront_id, staff_user_id=actor.staff_user_id)
            session.add(row)
            await session.flush()
        return row

    @classmethod
    async def status(cls, session, actor):
        row = await cls.get(session, actor)
        connected = bool(row and row.encrypted_credentials and row.last_error_code != "google_drive_access_denied")
        error = row.last_error_code if row else None
        if connected:
            try:
                CallDriveCredentialCipher.decrypt(row.encrypted_credentials, tenant_id=row.tenant_id, provider=cls.cipher_provider(row))
            except DocumentDriveConnectionError as exc:
                error, connected = exc.code, False
        return CallDriveStatus(connected=connected, pipeline_enabled=settings.CALL_RECORDINGS_ENABLED, transcription_configured=bool(settings.CALL_RECORDINGS_TRANSCRIPTION_API_KEY.strip()), account_label=row.account_label if row else None, folder_id=row.folder_id if row else None, folder_name=row.folder_name if row else None, folder_url=f"https://drive.google.com/drive/folders/{row.folder_id}" if row and row.folder_id else None, auto_poll_enabled=row.auto_poll_enabled if row else False, last_error_code=error, transcription_model=settings.CALL_RECORDINGS_TRANSCRIPTION_MODEL, structure_model=settings.DEEPSEEK_MODEL)

    @classmethod
    async def authorize(cls, session, actor, credentials, *, provider=None):
        await require_live_call_actor(session, actor, write=True)
        provider = provider or get_call_drive_provider()
        token = await provider.access_token(credentials)
        label = await provider.adapter(token).account_label()
        row = await cls.get(session, actor, create=True, for_update=True)
        if row.account_label != label:
            row.folder_id, row.folder_name, row.page_token = None, None, None
        row.auto_poll_enabled = False
        row.account_label = label
        row.encrypted_credentials = CallDriveCredentialCipher.encrypt(credentials, tenant_id=row.tenant_id, provider=cls.cipher_provider(row))
        row.credentials_fingerprint = CallDriveCredentialCipher.fingerprint(credentials)
        row.last_error_code = None
        session.add(row)
        await session.commit()
        return await cls.status(session, actor)

    @classmethod
    async def adapter(cls, session, actor, *, provider=None):
        row = await cls.get(session, actor, for_update=True)
        if row is None or not row.encrypted_credentials:
            raise CallDriveError("call_drive_not_connected", "Подключите личный Google Диск для записей", status_code=409)
        credentials = CallDriveCredentialCipher.decrypt(row.encrypted_credentials, tenant_id=row.tenant_id, provider=cls.cipher_provider(row))
        provider = provider or get_call_drive_provider()
        try:
            token = await provider.access_token(credentials)
        except DocumentDriveConnectionError as exc:
            row.last_error_code = exc.code
            session.add(row)
            await session.commit()
            raise
        # Refresh credentials in the same owner-bound envelope before releasing
        # the DB connection for Drive/AI I/O.
        row.encrypted_credentials = CallDriveCredentialCipher.encrypt(credentials, tenant_id=row.tenant_id, provider=cls.cipher_provider(row))
        row.credentials_fingerprint = CallDriveCredentialCipher.fingerprint(credentials)
        row.last_error_code = None
        session.add(row)
        await session.commit()
        return provider.adapter(token)

    @classmethod
    async def configure(cls, session, actor, payload: CallFolderPayload, *, provider=None):
        await require_live_call_actor(session, actor, write=True)
        adapter = await cls.adapter(session, actor, provider=provider)
        folder = await adapter.folder(payload.folder_id)
        row = await cls.get(session, actor, for_update=True)
        if row.folder_id != payload.folder_id:
            row.page_token = None
        row.folder_id, row.folder_name = payload.folder_id, str(folder.get("name") or "Папка записей")[:300]
        row.auto_poll_enabled = payload.auto_poll_enabled
        session.add(row)
        await session.commit()
        return await cls.status(session, actor)

    @classmethod
    async def disconnect(cls, session, actor):
        await require_live_call_actor(session, actor, write=True)
        row = await cls.get(session, actor, for_update=True)
        if row:
            row.encrypted_credentials = None
            row.credentials_fingerprint = ""
            row.auto_poll_enabled = False
            session.add(row)
            await session.commit()
        return await cls.status(session, actor)

    @staticmethod
    def require_enabled():
        if not settings.CALL_RECORDINGS_ENABLED:
            raise CallDriveError("call_pipeline_disabled", "Обработка звонков выключена на сервере", status_code=503)
