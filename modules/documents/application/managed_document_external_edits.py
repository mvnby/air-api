"""Round-trip editing for native managed-document drafts."""

from __future__ import annotations

from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import DocumentArtifact, DocumentExternalEditSession, Order, OrderDocument
from models.common import OrderStatus
from models.tenancy import TenantScope
from modules.documents.domain import DocumentStatus
from modules.documents.infrastructure.artifact_storage import (
    DocumentArtifactStorage,
)
from modules.documents.infrastructure.external_edit_provider import (
    DOCX_CONTENT_TYPE,
    ExternalEditProvider,
)
from modules.documents.infrastructure.template_source_storage import TemplateSourceStorage

from .artifact_helpers import artifact_row, stored_artifact
from .editable_draft import (
    official_placeholder_counts,
    render_editable_draft,
    validate_editable_draft,
)
from .errors import ManagedDocumentConflictError, ManagedDocumentNotFoundError
from .external_edit_sessions import (
    ExternalEditProviderError,
    ExternalEditSessionConflictError,
    ExternalEditSessionNotFoundError,
)
from .external_edit_support import (
    add_external_edit_sync_audit,
    claim_remote_initialization,
    external_edit_lease_is_live,
    lock_remote_initialization_result,
    record_external_edit_error,
    sync_request_fingerprint,
    utc_now as _utc_now,
    validate_external_docx_metadata,
)
from .template_selection import load_document_template_version
from .template_versions import MAX_NATIVE_TEMPLATE_BYTES, preflight_native_docx


class ManagedDocumentExternalEditSessionService:
    """Keep the editable Drive copy subordinate to the CRM draft and artifacts."""

    @classmethod
    async def ensure_session(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
        template_storage: TemplateSourceStorage,
        artifact_storage: DocumentArtifactStorage,
        provider: ExternalEditProvider,
        staff_user_id: int | None = None,
    ) -> DocumentExternalEditSession:
        document = await cls._editable_draft(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
        )
        source_artifact = await cls._ensure_source_artifact(
            session,
            tenant_scope=tenant_scope,
            document=document,
            template_storage=template_storage,
            artifact_storage=artifact_storage,
        )
        stored_source_artifact = stored_artifact(source_artifact)
        source_filename = source_artifact.filename
        edit_session = await cls._find_session(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            provider_name=provider.provider_name,
            provider_connection_id=provider.connection_id,
        )
        if edit_session is None:
            edit_session = DocumentExternalEditSession(
                tenant_id=tenant_scope.tenant_id,
                subject_type="document_artifact",
                document_artifact_id=source_artifact.id,
                provider=provider.provider_name,
                provider_connection_id=provider.connection_id,
                base_checksum_sha256=source_artifact.checksum_sha256,
                status="syncing",
                created_by_staff_user_id=staff_user_id,
            )
            session.add(edit_session)
            await cls._commit(session)
            await session.refresh(edit_session)
        cls._require_connection(edit_session, provider)

        if edit_session.remote_file_id:
            return await cls._refresh(session, edit_session, provider)
        edit_session, initialization_key = await claim_remote_initialization(
            session,
            edit_session,
            conflict_error=ExternalEditSessionConflictError,
        )
        if initialization_key is None:
            return await cls._refresh(session, edit_session, provider)

        try:
            content = await artifact_storage.read(stored_source_artifact)
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
                "Не удалось подготовить черновик в Google Docs"
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
        edit_session.last_synced_at = _utc_now()
        edit_session.status = "ready"
        edit_session.active_sync_key = None
        edit_session.detail = None
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
        document_id: int,
        provider: ExternalEditProvider,
    ) -> DocumentExternalEditSession:
        await cls._editable_draft(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
        )
        edit_session = await cls._find_session(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            provider_name=provider.provider_name,
            provider_connection_id=provider.connection_id,
        )
        if edit_session is None:
            raise ExternalEditSessionNotFoundError(
                "Сессия онлайн-редактирования черновика не найдена"
            )
        cls._require_connection(edit_session, provider)
        if not edit_session.remote_file_id:
            return edit_session
        return await cls._refresh(session, edit_session, provider)

    @classmethod
    async def sync(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
        expected_base_checksum_sha256: str,
        expected_remote_revision: str,
        idempotency_key: str,
        artifact_storage: DocumentArtifactStorage,
        provider: ExternalEditProvider,
        staff_user_id: int | None = None,
        actor_username: str | None = None,
    ) -> DocumentExternalEditSession:
        expected_checksum = _checksum(expected_base_checksum_sha256)
        expected_revision = _required(expected_remote_revision, "Версия файла Google", 500)
        sync_key = _required(idempotency_key, "Ключ операции", 160)
        request_fingerprint = sync_request_fingerprint(
            base_checksum_sha256=expected_checksum,
            remote_revision=expected_revision,
        )
        document = await cls._editable_draft(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            lock=True,
        )
        edit_session = await cls._find_session(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            provider_name=provider.provider_name,
            provider_connection_id=provider.connection_id,
            lock=True,
        )
        if edit_session is None:
            raise ExternalEditSessionNotFoundError(
                "Сессия онлайн-редактирования черновика не найдена"
            )
        cls._require_connection(edit_session, provider)
        if edit_session.last_sync_key == sync_key:
            if edit_session.last_sync_fingerprint != request_fingerprint:
                raise ExternalEditSessionConflictError(
                    "Ключ синхронизации уже использован для другой версии файла"
                )
            return edit_session
        if edit_session.base_checksum_sha256 != expected_checksum:
            raise ExternalEditSessionConflictError(
                "Черновик уже синхронизирован в другой вкладке; обновите данные"
            )
        if (
            external_edit_lease_is_live(edit_session)
            and edit_session.active_sync_key != sync_key
        ):
            raise ExternalEditSessionConflictError(
                "Другая синхронизация черновика ещё выполняется"
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
            raise ExternalEditSessionConflictError("Файл Google ещё не подготовлен")

        edit_session.status = "syncing"
        edit_session.active_sync_key = sync_key
        edit_session.active_sync_fingerprint = request_fingerprint
        edit_session.detail = None
        edit_session.updated_at = _utc_now()
        session.add(edit_session)
        await cls._commit(session)

        try:
            downloaded = await provider.download_docx(edit_session.remote_file_id)
            validate_external_docx_metadata(
                downloaded.metadata,
                expected_file_id=edit_session.remote_file_id,
                expected_edit_session_id=edit_session.id,
            )
        except Exception as exc:
            await record_external_edit_error(session, edit_session)
            raise ExternalEditProviderError(
                "Не удалось получить изменённый черновик из Google Docs"
            ) from exc

        if downloaded.metadata.revision != expected_revision:
            cls._apply_metadata(edit_session, downloaded.metadata)
            edit_session.remote_revision = downloaded.metadata.revision
            edit_session.status = "changed"
            edit_session.active_sync_key = None
            edit_session.active_sync_fingerprint = None
            edit_session.detail = (
                "Файл изменился после последней проверки; обновите данные и повторите"
            )
            edit_session.updated_at = _utc_now()
            session.add(edit_session)
            await cls._commit(session)
            raise ExternalEditSessionConflictError(edit_session.detail)

        content = downloaded.content
        try:
            if len(content) > MAX_NATIVE_TEMPLATE_BYTES:
                raise ManagedDocumentConflictError("DOCX превышает допустимый размер")
            preflight_native_docx(content)
            template, version = await load_document_template_version(
                session,
                tenant_scope=tenant_scope,
                document=document,
            )
            del template
            required_counts = await cls._required_placeholder_counts(
                session,
                edit_session=edit_session,
                document_id=document_id,
                tenant_id=tenant_scope.tenant_id,
                placeholder_schema=version.placeholder_schema or {},
                artifact_storage=artifact_storage,
            )
            validate_editable_draft(
                source=content,
                placeholder_schema=version.placeholder_schema or {},
                required_placeholder_counts=required_counts,
            )
        except Exception as exc:
            await record_external_edit_error(session, edit_session)
            raise ManagedDocumentConflictError(
                "Изменённый DOCX не прошёл проверку перед сохранением"
            ) from exc
        content_checksum = sha256(content).hexdigest()
        if content_checksum == expected_checksum:
            cls._finish_sync(
                edit_session,
                downloaded.metadata,
                sync_key,
                request_fingerprint,
                content_checksum,
                staff_user_id,
            )
            session.add(edit_session)
            add_external_edit_sync_audit(
                session,
                tenant_scope=tenant_scope,
                edit_session=edit_session,
                actor_staff_user_id=staff_user_id,
                actor_username=actor_username,
                action="order_document.google_sync",
                entity_type="order_document",
                entity_id=document_id,
            )
            await cls._commit(session)
            await session.refresh(edit_session)
            return edit_session

        try:
            stored = await artifact_storage.save(
                tenant_id=tenant_scope.tenant_id,
                document_id=document_id,
                kind="source_docx",
                filename=downloaded.metadata.filename,
                content_type=DOCX_CONTENT_TYPE,
                content=content,
            )
        except Exception as exc:
            await record_external_edit_error(session, edit_session)
            raise ExternalEditProviderError(
                "Не удалось сохранить изменённый черновик в CRM"
            ) from exc

        # Re-lock after the remote/storage calls and compare the authoritative base.
        await cls._editable_draft(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            lock=True,
        )
        edit_session = await cls._find_session(
            session,
            tenant_scope=tenant_scope,
            document_id=document_id,
            provider_name=provider.provider_name,
            provider_connection_id=provider.connection_id,
            lock=True,
        )
        if edit_session is None:
            raise ExternalEditSessionNotFoundError(
                "Сессия онлайн-редактирования черновика не найдена"
            )
        if edit_session.last_sync_key == sync_key:
            if edit_session.last_sync_fingerprint != request_fingerprint:
                raise ExternalEditSessionConflictError(
                    "Ключ синхронизации уже использован для другой версии файла"
                )
            return edit_session
        current = await cls._source_artifact(
            session, tenant_scope.tenant_id, document_id, lock=True
        )
        if current is None or current.checksum_sha256 != expected_checksum:
            raise ExternalEditSessionConflictError(
                "Черновик уже синхронизирован в другой вкладке; обновите данные"
            )
        current.is_authoritative = False
        session.add(current)
        await session.flush()
        replacement = artifact_row(stored)
        session.add(replacement)
        await session.flush()
        cls._finish_sync(
            edit_session,
            downloaded.metadata,
            sync_key,
            request_fingerprint,
            content_checksum,
            staff_user_id,
        )
        session.add(edit_session)
        add_external_edit_sync_audit(
            session,
            tenant_scope=tenant_scope,
            edit_session=edit_session,
            actor_staff_user_id=staff_user_id,
            actor_username=actor_username,
            action="order_document.google_sync",
            entity_type="order_document",
            entity_id=document_id,
            change_set={"new_document_artifact_id": str(replacement.id)},
        )
        await cls._commit(session)
        await session.refresh(edit_session)
        return edit_session

    @classmethod
    async def _ensure_source_artifact(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document: OrderDocument,
        template_storage: TemplateSourceStorage,
        artifact_storage: DocumentArtifactStorage,
    ) -> DocumentArtifact:
        existing = await cls._source_artifact(
            session, tenant_scope.tenant_id, int(document.id)
        )
        if existing is not None:
            return existing
        template, version = await load_document_template_version(
            session,
            tenant_scope=tenant_scope,
            document=document,
        )
        source = await template_storage.read_persisted(
            tenant_id=tenant_scope.tenant_id,
            template_id=int(template.id),
            version=version.version,
            storage_key=version.source_storage_key,
            filename=str(version.source_filename or "template.docx"),
            checksum_sha256=version.checksum_sha256,
        )
        editable = render_editable_draft(
            template=template,
            version=version,
            source=source,
            snapshot=document.render_snapshot or {},
        )
        stored = await artifact_storage.save(
            tenant_id=tenant_scope.tenant_id,
            document_id=int(document.id),
            kind="source_docx",
            filename=f"draft-{document.internal_reference}.docx",
            content_type=DOCX_CONTENT_TYPE,
            content=editable,
        )
        # Another request may have completed while rendering.
        await cls._editable_draft(
            session,
            tenant_scope=tenant_scope,
            document_id=int(document.id),
            lock=True,
        )
        existing = await cls._source_artifact(
            session, tenant_scope.tenant_id, int(document.id), lock=True
        )
        if existing is not None:
            return existing
        row = artifact_row(stored)
        session.add(row)
        await cls._commit(session)
        await session.refresh(row)
        return row

    @staticmethod
    async def _editable_draft(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
        lock: bool = False,
    ) -> OrderDocument:
        statement = (
            select(OrderDocument)
            .join(Order, Order.id == OrderDocument.order_id)
            .where(
                OrderDocument.id == document_id,
                OrderDocument.tenant_id == tenant_scope.tenant_id,
                Order.tenant_id == tenant_scope.tenant_id,
                Order.storefront_id == tenant_scope.storefront_id,
            )
        )
        if lock:
            statement = statement.with_for_update()
        document = (await session.execute(statement)).scalar_one_or_none()
        if document is None:
            raise ManagedDocumentNotFoundError("Документ не найден")
        order = await session.get(Order, document.order_id)
        if order is None or order.status == OrderStatus.CLOSED:
            raise ManagedDocumentConflictError(
                "Заказ завершён: документ доступен только для просмотра"
            )
        if (
            document.status != DocumentStatus.DRAFT.value
            or document.official_number
            or document.issued_at
        ):
            raise ManagedDocumentConflictError(
                "Онлайн редактируется только черновик до выпуска"
            )
        if not document.template_version_id or not document.render_snapshot:
            raise ManagedDocumentConflictError(
                "Черновик не относится к нативному документному контуру"
            )
        return document

    @staticmethod
    async def _source_artifact(
        session: AsyncSession,
        tenant_id: int,
        document_id: int,
        *,
        lock: bool = False,
    ) -> DocumentArtifact | None:
        statement = select(DocumentArtifact).where(
            DocumentArtifact.tenant_id == tenant_id,
            DocumentArtifact.order_document_id == document_id,
            DocumentArtifact.kind == "source_docx",
            DocumentArtifact.is_authoritative.is_(True),
        )
        if lock:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def _required_placeholder_counts(
        session: AsyncSession,
        *,
        edit_session: DocumentExternalEditSession,
        document_id: int,
        tenant_id: int,
        placeholder_schema,
        artifact_storage: DocumentArtifactStorage,
    ) -> dict[str, int]:
        anchor = await session.get(
            DocumentArtifact, edit_session.document_artifact_id
        )
        if (
            anchor is None
            or anchor.tenant_id != tenant_id
            or anchor.order_document_id != document_id
            or anchor.kind != "source_docx"
        ):
            raise ManagedDocumentConflictError(
                "Исходная редакция черновика недоступна для проверки"
            )
        source = await artifact_storage.read(stored_artifact(anchor))
        return official_placeholder_counts(
            source=source,
            placeholder_schema=placeholder_schema,
        )

    @staticmethod
    async def _find_session(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        document_id: int,
        provider_name: str,
        provider_connection_id: str,
        lock: bool = False,
    ) -> DocumentExternalEditSession | None:
        statement = (
            select(DocumentExternalEditSession)
            .join(
                DocumentArtifact,
                DocumentArtifact.id
                == DocumentExternalEditSession.document_artifact_id,
            )
            .join(OrderDocument, OrderDocument.id == DocumentArtifact.order_document_id)
            .join(Order, Order.id == OrderDocument.order_id)
            .where(
                DocumentExternalEditSession.tenant_id == tenant_scope.tenant_id,
                DocumentExternalEditSession.subject_type == "document_artifact",
                DocumentExternalEditSession.provider == provider_name,
                DocumentExternalEditSession.provider_connection_id
                == provider_connection_id,
                DocumentArtifact.tenant_id == tenant_scope.tenant_id,
                DocumentArtifact.order_document_id == document_id,
                OrderDocument.tenant_id == tenant_scope.tenant_id,
                Order.tenant_id == tenant_scope.tenant_id,
                Order.storefront_id == tenant_scope.storefront_id,
            )
            .order_by(DocumentExternalEditSession.created_at.desc())
        )
        if lock:
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalars().first()

    @staticmethod
    async def _refresh(session, edit_session, provider):
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
                "Не удалось проверить черновик в Google Docs"
            ) from exc
        baseline = edit_session.last_sync_remote_revision or edit_session.remote_revision
        ManagedDocumentExternalEditSessionService._apply_metadata(edit_session, metadata)
        edit_session.remote_revision = metadata.revision
        edit_session.status = "changed" if metadata.revision != baseline else "ready"
        edit_session.detail = None
        edit_session.active_sync_key = None
        edit_session.active_sync_fingerprint = None
        edit_session.updated_at = _utc_now()
        session.add(edit_session)
        await ManagedDocumentExternalEditSessionService._commit(session)
        await session.refresh(edit_session)
        return edit_session

    @staticmethod
    def _require_connection(edit_session, provider):
        if edit_session.provider_connection_id != provider.connection_id:
            raise ExternalEditSessionConflictError(
                "Google был переподключён; создайте новую сессию редактирования"
            )

    @staticmethod
    def _apply_metadata(edit_session, metadata):
        edit_session.remote_file_id = metadata.file_id
        edit_session.edit_url = metadata.edit_url
        edit_session.remote_filename = metadata.filename
        edit_session.remote_mime_type = metadata.mime_type
        edit_session.remote_modified_at = metadata.modified_at

    @staticmethod
    def _finish_sync(
        edit_session,
        metadata,
        sync_key,
        request_fingerprint,
        checksum,
        staff_user_id,
    ):
        ManagedDocumentExternalEditSessionService._apply_metadata(edit_session, metadata)
        edit_session.base_checksum_sha256 = checksum
        edit_session.remote_revision = metadata.revision
        edit_session.last_sync_remote_revision = metadata.revision
        edit_session.last_sync_key = sync_key
        edit_session.last_sync_fingerprint = request_fingerprint
        edit_session.active_sync_key = None
        edit_session.active_sync_fingerprint = None
        edit_session.last_synced_by_staff_user_id = staff_user_id
        edit_session.status = "ready"
        edit_session.detail = None
        edit_session.last_synced_at = _utc_now()
        edit_session.updated_at = _utc_now()

    @staticmethod
    async def _commit(session):
        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise ExternalEditSessionConflictError(
                "Не удалось сохранить сессию онлайн-редактирования"
            ) from exc


def _checksum(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError("Ожидаемая контрольная сумма некорректна")
    return normalized


def _required(value: str, label: str, limit: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > limit:
        raise ValueError(f"{label}: обязательное значение некорректно")
    return normalized
