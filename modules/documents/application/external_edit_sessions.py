"""Audited, provider-neutral round-trip editing for document sources."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    DocumentExternalEditSession,
    DocumentTemplate,
    DocumentTemplateVersion,
)
from models.tenancy import TenantScope
from modules.documents.infrastructure.external_edit_provider import (
    ExternalEditFileMetadata,
    ExternalEditProvider,
)
from modules.documents.infrastructure.template_source_storage import (
    TemplateSourceStorage,
)

from .native_template_discovery import discover_native_placeholder_contract
from .template_versions import (
    MAX_NATIVE_TEMPLATE_BYTES,
    NativeTemplateVersionService,
    TemplateVersionConflictError,
    TemplateVersionError,
)
from .external_edit_support import (
    add_external_edit_sync_audit,
    claim_remote_initialization,
    external_edit_lease_is_live,
    lock_remote_initialization_result,
    record_external_edit_error,
    sync_request_fingerprint,
    utc_now as _utc_now,
    validate_external_docx_download,
    validate_external_docx_metadata,
)


class ExternalEditSessionError(ValueError):
    pass


class ExternalEditSessionNotFoundError(ExternalEditSessionError):
    pass


class ExternalEditSessionConflictError(ExternalEditSessionError):
    pass


class ExternalEditProviderError(ExternalEditSessionError):
    pass


@dataclass(frozen=True, slots=True)
class TemplateExternalEditSyncResult:
    edit_session: DocumentExternalEditSession
    new_template_version: DocumentTemplateVersion | None


class TemplateExternalEditSessionService:
    """Google-ready application flow without coupling lifecycle to Google APIs."""

    @classmethod
    async def ensure_session(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        template_id: int,
        version_id: int,
        source_storage: TemplateSourceStorage,
        provider: ExternalEditProvider,
        staff_user_id: int | None = None,
    ) -> DocumentExternalEditSession:
        version = await NativeTemplateVersionService.get_version(
            session,
            tenant_scope=tenant_scope,
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
        )
        cls._require_native_docx(version)
        source_version_number = version.version
        source_storage_key = version.source_storage_key
        source_filename = str(version.source_filename or "template.docx")
        source_checksum = version.checksum_sha256
        provider_name, connection_id = cls._provider_identity(provider)
        edit_session = await cls._find_scoped_session(
            session,
            tenant_scope=tenant_scope,
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
            provider_name=provider_name,
            connection_id=connection_id,
        )
        if edit_session is None:
            edit_session = DocumentExternalEditSession(
                tenant_id=tenant_scope.tenant_id,
                subject_type="template_version",
                template_version_id=int(version.id),
                provider=provider_name,
                provider_connection_id=connection_id,
                base_checksum_sha256=version.checksum_sha256,
                status="syncing",
                created_by_staff_user_id=staff_user_id,
            )
            session.add(edit_session)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                edit_session = await cls._find_scoped_session(
                    session,
                    tenant_scope=tenant_scope,
                    legal_entity_id=legal_entity_id,
                    template_id=template_id,
                    version_id=version_id,
                    provider_name=provider_name,
                    connection_id=connection_id,
                )
                if edit_session is None:
                    raise ExternalEditSessionConflictError(
                        "Не удалось создать сессию онлайн-редактирования"
                    )

        cls._require_connection(edit_session, connection_id)
        if edit_session.remote_file_id:
            return await cls._refresh_existing(
                session,
                edit_session=edit_session,
                provider=provider,
            )
        edit_session, initialization_key = await claim_remote_initialization(
            session,
            edit_session,
            conflict_error=ExternalEditSessionConflictError,
        )
        if initialization_key is None:
            return await cls._refresh_existing(
                session,
                edit_session=edit_session,
                provider=provider,
            )

        try:
            content = await source_storage.read_persisted(
                tenant_id=tenant_scope.tenant_id,
                template_id=template_id,
                version=source_version_number,
                storage_key=source_storage_key,
                filename=source_filename,
                checksum_sha256=source_checksum,
            )
            metadata = await provider.ensure_docx(
                edit_session_id=edit_session.id,
                filename=source_filename,
                content=content,
            )
            validate_external_docx_metadata(
                metadata, expected_edit_session_id=edit_session.id
            )
        except Exception as exc:
            await record_external_edit_error(session, edit_session)
            raise ExternalEditProviderError(
                "Не удалось подготовить DOCX в онлайн-редакторе"
            ) from exc

        edit_session = await lock_remote_initialization_result(
            session,
            edit_session,
            claim_key=initialization_key,
            conflict_error=ExternalEditSessionConflictError,
        )
        cls._apply_metadata(edit_session, metadata)
        edit_session.remote_revision = metadata.revision
        edit_session.last_sync_remote_revision = metadata.revision
        edit_session.status = "ready"
        edit_session.active_sync_key = None
        edit_session.detail = None
        edit_session.last_synced_at = _utc_now()
        edit_session.updated_at = _utc_now()
        session.add(edit_session)
        await cls._commit(session)
        await session.refresh(edit_session)
        return edit_session

    @classmethod
    async def get_session(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        template_id: int,
        version_id: int,
        provider: ExternalEditProvider,
    ) -> DocumentExternalEditSession:
        provider_name, connection_id = cls._provider_identity(provider)
        edit_session = await cls._find_scoped_session(
            session,
            tenant_scope=tenant_scope,
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
            provider_name=provider_name,
            connection_id=connection_id,
        )
        if edit_session is None:
            raise ExternalEditSessionNotFoundError(
                "Сессия онлайн-редактирования не найдена"
            )
        cls._require_connection(edit_session, connection_id)
        if not edit_session.remote_file_id:
            return edit_session
        return await cls._refresh_existing(
            session,
            edit_session=edit_session,
            provider=provider,
        )

    @classmethod
    async def sync(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        template_id: int,
        version_id: int,
        expected_base_checksum_sha256: str,
        expected_remote_revision: str,
        idempotency_key: str,
        source_storage: TemplateSourceStorage,
        provider: ExternalEditProvider,
        staff_user_id: int | None = None,
        actor_username: str | None = None,
    ) -> TemplateExternalEditSyncResult:
        expected_checksum = _checksum(expected_base_checksum_sha256)
        expected_revision = _required_text(
            expected_remote_revision, "Версия файла Google", 500
        )
        sync_key = _required_text(idempotency_key, "Ключ операции", 160)
        request_fingerprint = sync_request_fingerprint(
            base_checksum_sha256=expected_checksum,
            remote_revision=expected_revision,
        )
        provider_name, connection_id = cls._provider_identity(provider)
        edit_session = await cls._find_scoped_session(
            session,
            tenant_scope=tenant_scope,
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
            provider_name=provider_name,
            connection_id=connection_id,
            lock=True,
        )
        if edit_session is None:
            raise ExternalEditSessionNotFoundError(
                "Сессия онлайн-редактирования не найдена"
            )
        cls._require_connection(edit_session, connection_id)
        completed = await cls._completed_sync_result(
            session,
            edit_session=edit_session,
            template_id=template_id,
            sync_key=sync_key,
            request_fingerprint=request_fingerprint,
        )
        if completed is not None:
            return completed
        if edit_session.base_checksum_sha256 != expected_checksum:
            raise ExternalEditSessionConflictError(
                "Шаблон уже синхронизирован в другой вкладке; обновите данные"
            )
        if (
            external_edit_lease_is_live(edit_session)
            and edit_session.active_sync_key != sync_key
        ):
            raise ExternalEditSessionConflictError(
                "Другая синхронизация шаблона ещё выполняется"
            )
        if (
            edit_session.active_sync_key == sync_key
            and edit_session.active_sync_fingerprint
            and edit_session.active_sync_fingerprint != request_fingerprint
        ):
            raise ExternalEditSessionConflictError(
                "Ключ синхронизации уже используется для другой версии файла"
            )
        if not edit_session.remote_file_id:
            raise ExternalEditSessionConflictError(
                "Файл онлайн-редактора ещё не подготовлен"
            )

        edit_session.status = "syncing"
        edit_session.active_sync_key = sync_key
        edit_session.active_sync_fingerprint = request_fingerprint
        edit_session.detail = None
        edit_session.updated_at = _utc_now()
        session.add(edit_session)
        await cls._commit(session)

        try:
            downloaded = await provider.download_docx(edit_session.remote_file_id)
            validate_external_docx_download(
                downloaded,
                expected_file_id=edit_session.remote_file_id,
                expected_edit_session_id=edit_session.id,
                max_bytes=MAX_NATIVE_TEMPLATE_BYTES,
            )
        except Exception as exc:
            await record_external_edit_error(session, edit_session)
            raise ExternalEditProviderError(
                "Не удалось получить изменённый DOCX из онлайн-редактора"
            ) from exc

        if downloaded.metadata.revision != expected_revision:
            cls._apply_metadata(edit_session, downloaded.metadata)
            edit_session.remote_revision = downloaded.metadata.revision
            edit_session.status = "changed"
            edit_session.active_sync_key = None
            edit_session.active_sync_fingerprint = None
            edit_session.detail = (
                "Файл изменился после последней проверки; обновите данные и "
                "повторите синхронизацию"
            )
            edit_session.updated_at = _utc_now()
            session.add(edit_session)
            await cls._commit(session)
            raise ExternalEditSessionConflictError(edit_session.detail)

        content_checksum = sha256(downloaded.content).hexdigest()
        if content_checksum == expected_checksum:
            cls._finish_sync(
                edit_session,
                downloaded.metadata,
                checksum=content_checksum,
                sync_key=sync_key,
                request_fingerprint=request_fingerprint,
                imported_version_id=None,
                staff_user_id=staff_user_id,
            )
            session.add(edit_session)
            add_external_edit_sync_audit(
                session,
                tenant_scope=tenant_scope,
                edit_session=edit_session,
                actor_staff_user_id=staff_user_id,
                actor_username=actor_username,
                action="document_template.google_sync",
                entity_type="document_template",
                entity_id=template_id,
                change_set={"source_template_version_id": version_id},
            )
            await cls._commit(session)
            await session.refresh(edit_session)
            return TemplateExternalEditSyncResult(edit_session, None)

        # The provider call runs outside a DB transaction. Re-check the baseline
        # under a row lock before creating the immutable CRM revision.
        edit_session = await cls._find_scoped_session(
            session,
            tenant_scope=tenant_scope,
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
            provider_name=provider_name,
            connection_id=connection_id,
            lock=True,
        )
        if edit_session is None:
            raise ExternalEditSessionNotFoundError(
                "Сессия онлайн-редактирования не найдена"
            )
        completed = await cls._completed_sync_result(
            session,
            edit_session=edit_session,
            template_id=template_id,
            sync_key=sync_key,
            request_fingerprint=request_fingerprint,
        )
        if completed is not None:
            return completed
        if edit_session.base_checksum_sha256 != expected_checksum:
            raise ExternalEditSessionConflictError(
                "Шаблон уже синхронизирован в другой вкладке; обновите данные"
            )

        try:
            placeholder_contract = discover_native_placeholder_contract(
                downloaded.content
            )
            new_version = await NativeTemplateVersionService.upload_native_docx_version(
                session,
                tenant_scope=tenant_scope,
                legal_entity_id=legal_entity_id,
                template_id=template_id,
                filename=downloaded.metadata.filename,
                content=downloaded.content,
                placeholder_contract=placeholder_contract,
                storage=source_storage,
                change_note="Изменения из Google Docs",
                commit=False,
            )
            cls._finish_sync(
                edit_session,
                downloaded.metadata,
                checksum=content_checksum,
                sync_key=sync_key,
                request_fingerprint=request_fingerprint,
                imported_version_id=int(new_version.id),
                staff_user_id=staff_user_id,
            )
            session.add(edit_session)
            add_external_edit_sync_audit(
                session,
                tenant_scope=tenant_scope,
                edit_session=edit_session,
                actor_staff_user_id=staff_user_id,
                actor_username=actor_username,
                action="document_template.google_sync",
                entity_type="document_template",
                entity_id=template_id,
                change_set={
                    "source_template_version_id": version_id,
                    "new_template_version_id": int(new_version.id),
                },
            )
            await cls._commit(session)
        except (TemplateVersionError, TemplateVersionConflictError):
            edit_session_id = edit_session.id
            await session.rollback()
            edit_session = await cls._find_by_id(
                session, tenant_scope.tenant_id, edit_session_id
            )
            if edit_session is not None:
                edit_session.status = "error"
                edit_session.detail = "Изменённый DOCX не прошёл проверку шаблона"
                edit_session.active_sync_key = None
                edit_session.active_sync_fingerprint = None
                edit_session.updated_at = _utc_now()
                session.add(edit_session)
                await cls._commit(session)
            raise

        await session.refresh(edit_session)
        await session.refresh(new_version)
        return TemplateExternalEditSyncResult(edit_session, new_version)

    @classmethod
    async def _refresh_existing(
        cls,
        session: AsyncSession,
        *,
        edit_session: DocumentExternalEditSession,
        provider: ExternalEditProvider,
    ) -> DocumentExternalEditSession:
        if external_edit_lease_is_live(edit_session):
            return edit_session
        try:
            metadata = await provider.get_metadata(str(edit_session.remote_file_id))
            validate_external_docx_metadata(
                metadata,
                expected_file_id=edit_session.remote_file_id,
                expected_edit_session_id=edit_session.id,
            )
        except Exception as exc:
            await record_external_edit_error(session, edit_session)
            raise ExternalEditProviderError(
                "Не удалось проверить файл онлайн-редактора"
            ) from exc
        baseline_revision = (
            edit_session.last_sync_remote_revision or edit_session.remote_revision
        )
        changed = metadata.revision != baseline_revision
        cls._apply_metadata(edit_session, metadata)
        edit_session.remote_revision = metadata.revision
        edit_session.status = "changed" if changed else "ready"
        edit_session.detail = None
        edit_session.active_sync_key = None
        edit_session.active_sync_fingerprint = None
        edit_session.updated_at = _utc_now()
        session.add(edit_session)
        await cls._commit(session)
        await session.refresh(edit_session)
        return edit_session

    @staticmethod
    async def _find_scoped_session(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        legal_entity_id: int,
        template_id: int,
        version_id: int,
        provider_name: str,
        connection_id: str,
        lock: bool = False,
    ) -> DocumentExternalEditSession | None:
        statement = (
            select(DocumentExternalEditSession)
            .join(
                DocumentTemplateVersion,
                DocumentTemplateVersion.id
                == DocumentExternalEditSession.template_version_id,
            )
            .join(
                DocumentTemplate,
                DocumentTemplate.id == DocumentTemplateVersion.template_id,
            )
            .where(
                DocumentExternalEditSession.tenant_id == tenant_scope.tenant_id,
                DocumentExternalEditSession.subject_type == "template_version",
                DocumentExternalEditSession.provider == provider_name,
                DocumentExternalEditSession.provider_connection_id == connection_id,
                DocumentTemplate.tenant_id == tenant_scope.tenant_id,
                DocumentTemplate.legal_entity_id == legal_entity_id,
                DocumentTemplate.id == template_id,
                DocumentTemplateVersion.id == version_id,
            )
        )
        if lock:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def _find_by_id(
        session: AsyncSession, tenant_id: int, edit_session_id: str
    ) -> DocumentExternalEditSession | None:
        return (
            await session.execute(
                select(DocumentExternalEditSession).where(
                    DocumentExternalEditSession.id == edit_session_id,
                    DocumentExternalEditSession.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _completed_sync_result(
        session: AsyncSession,
        *,
        edit_session: DocumentExternalEditSession,
        template_id: int,
        sync_key: str,
        request_fingerprint: str,
    ) -> TemplateExternalEditSyncResult | None:
        if edit_session.last_sync_key != sync_key:
            return None
        if edit_session.last_sync_fingerprint != request_fingerprint:
            raise ExternalEditSessionConflictError(
                "Ключ синхронизации уже использован для другой версии файла"
            )
        if not edit_session.last_sync_remote_revision:
            raise ExternalEditSessionConflictError(
                "Предыдущая синхронизация не содержит полной информации о результате"
            )
        imported = None
        if edit_session.last_imported_template_version_id is not None:
            imported = (
                await session.execute(
                    select(DocumentTemplateVersion).where(
                        DocumentTemplateVersion.id
                        == edit_session.last_imported_template_version_id,
                        DocumentTemplateVersion.template_id == template_id,
                    )
                )
            ).scalar_one_or_none()
            if imported is None:
                raise ExternalEditSessionConflictError(
                    "Результат предыдущей синхронизации недоступен"
                )
        return TemplateExternalEditSyncResult(edit_session, imported)

    @staticmethod
    def _finish_sync(
        edit_session: DocumentExternalEditSession,
        metadata: ExternalEditFileMetadata,
        *,
        checksum: str,
        sync_key: str,
        request_fingerprint: str,
        imported_version_id: int | None,
        staff_user_id: int | None,
    ) -> None:
        TemplateExternalEditSessionService._apply_metadata(edit_session, metadata)
        edit_session.base_checksum_sha256 = checksum
        edit_session.remote_revision = metadata.revision
        edit_session.status = "ready"
        edit_session.detail = None
        edit_session.last_sync_key = sync_key
        edit_session.last_sync_fingerprint = request_fingerprint
        edit_session.active_sync_key = None
        edit_session.active_sync_fingerprint = None
        edit_session.last_sync_remote_revision = metadata.revision
        edit_session.last_imported_template_version_id = imported_version_id
        edit_session.last_synced_by_staff_user_id = staff_user_id
        edit_session.last_synced_at = _utc_now()
        edit_session.updated_at = _utc_now()

    @staticmethod
    def _apply_metadata(
        edit_session: DocumentExternalEditSession,
        metadata: ExternalEditFileMetadata,
    ) -> None:
        edit_session.remote_file_id = metadata.file_id
        edit_session.edit_url = metadata.edit_url
        edit_session.remote_filename = metadata.filename
        edit_session.remote_mime_type = metadata.mime_type
        edit_session.remote_modified_at = metadata.modified_at

    @staticmethod
    def _provider_identity(provider: ExternalEditProvider) -> tuple[str, str]:
        return (
            _required_text(provider.provider_name, "Провайдер", 40),
            _required_text(provider.connection_id, "Подключение", 160),
        )

    @staticmethod
    def _require_connection(
        edit_session: DocumentExternalEditSession, connection_id: str
    ) -> None:
        if edit_session.provider_connection_id != connection_id:
            raise ExternalEditSessionConflictError(
                "Файл связан с другим подключением Google; переподключите прежний аккаунт"
            )

    @staticmethod
    def _require_native_docx(version: DocumentTemplateVersion) -> None:
        if version.renderer != "docx":
            raise ExternalEditSessionError(
                "Онлайн-редактирование доступно только для DOCX шаблонов"
            )

    @staticmethod
    async def _commit(session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ExternalEditSessionConflictError(
                "Сессия онлайн-редактирования была изменена параллельно"
            ) from exc


def _required_text(value: object, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise ExternalEditSessionError(f"{label} имеет неверный формат")
    return normalized


def _checksum(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ExternalEditSessionError("Контрольная сумма имеет неверный формат")
    return normalized
