"""Load and validate a Google-edited source before official numbering."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    DocumentArtifact,
    DocumentExternalEditSession,
    Order,
    OrderDocument,
)
from models.tenancy import TenantScope
from modules.documents.infrastructure.artifact_storage import DocumentArtifactStorage
from modules.documents.infrastructure.external_edit_provider import (
    DOCX_CONTENT_TYPE,
    ExternalEditProvider,
)

from .artifact_helpers import stored_artifact
from .editable_draft import (
    EditableDraftError,
    official_placeholder_counts,
    validate_editable_draft,
)


@dataclass(frozen=True, slots=True)
class EditableDraftIssueSource:
    content: bytes
    required_placeholder_counts: dict[str, int]


async def load_editable_draft_for_issue(
    session: AsyncSession,
    *,
    tenant_id: int,
    document_id: int,
    source_artifact: DocumentArtifact,
    placeholder_schema: dict,
    artifact_storage: DocumentArtifactStorage,
    verified_remote_revision: str | None = None,
) -> EditableDraftIssueSource:
    """Lock the latest edit session and prove CRM bytes are safe to issue."""

    edit_session = (
        await session.execute(
            select(DocumentExternalEditSession)
            .join(
                DocumentArtifact,
                DocumentArtifact.id
                == DocumentExternalEditSession.document_artifact_id,
            )
            .where(
                DocumentExternalEditSession.tenant_id == tenant_id,
                DocumentExternalEditSession.subject_type == "document_artifact",
                DocumentArtifact.tenant_id == tenant_id,
                DocumentArtifact.order_document_id == document_id,
            )
            .order_by(DocumentExternalEditSession.created_at.desc())
            .with_for_update()
        )
    ).scalars().first()
    if edit_session is None:
        raise EditableDraftError(
            "Для редактируемого DOCX отсутствует сессия онлайн-редактора"
        )
    if edit_session.status == "changed":
        raise EditableDraftError("В Google Docs есть несинхронизированные изменения")
    if edit_session.status == "syncing":
        raise EditableDraftError("Синхронизация с Google Docs ещё выполняется")
    if edit_session.status == "error":
        raise EditableDraftError(
            "Последняя синхронизация с Google Docs завершилась ошибкой"
        )
    if edit_session.base_checksum_sha256 != source_artifact.checksum_sha256:
        raise EditableDraftError(
            "Редакция Google Docs не совпадает с текущим черновиком CRM"
        )
    synchronized_revision = (
        edit_session.last_sync_remote_revision or edit_session.remote_revision
    )
    if not synchronized_revision or verified_remote_revision != synchronized_revision:
        raise EditableDraftError(
            "Перед выпуском не подтверждена текущая версия Google Docs"
        )

    anchor_artifact = await session.get(
        DocumentArtifact, edit_session.document_artifact_id
    )
    if (
        anchor_artifact is None
        or anchor_artifact.tenant_id != tenant_id
        or anchor_artifact.order_document_id != document_id
        or anchor_artifact.kind != "source_docx"
    ):
        raise EditableDraftError(
            "Исходная редакция Google Docs недоступна для проверки"
        )
    anchor_source = await artifact_storage.read(stored_artifact(anchor_artifact))
    required_counts = official_placeholder_counts(
        source=anchor_source,
        placeholder_schema=placeholder_schema,
    )
    editable_source = await artifact_storage.read(stored_artifact(source_artifact))
    validate_editable_draft(
        source=editable_source,
        placeholder_schema=placeholder_schema,
        required_placeholder_counts=required_counts,
    )
    return EditableDraftIssueSource(
        content=editable_source,
        required_placeholder_counts=required_counts,
    )


async def verify_document_external_edit_before_issue(
    session: AsyncSession,
    *,
    tenant_scope: TenantScope,
    document_id: int,
    provider: ExternalEditProvider | None,
) -> str | None:
    """Refresh the remote revision immediately before the numbering transaction."""

    edit_session = await _scoped_edit_session(
        session,
        tenant_scope=tenant_scope,
        document_id=document_id,
        lock=False,
    )
    if edit_session is None:
        return None
    if provider is None:
        raise EditableDraftError(
            "Нельзя проверить Google Docs перед выпуском; восстановите подключение"
        )
    if (
        edit_session.provider != provider.provider_name
        or edit_session.provider_connection_id != provider.connection_id
        or not edit_session.remote_file_id
    ):
        raise EditableDraftError(
            "Черновик связан с другим подключением Google"
        )
    remote_file_id = str(edit_session.remote_file_id)
    edit_session_id = edit_session.id
    await session.commit()
    try:
        metadata = await provider.get_metadata(remote_file_id)
    except Exception as exc:
        raise EditableDraftError(
            "Google Docs не ответил при проверке черновика"
        ) from exc

    current = await _scoped_edit_session(
        session,
        tenant_scope=tenant_scope,
        document_id=document_id,
        lock=True,
    )
    if current is None or current.id != edit_session_id:
        raise EditableDraftError("Сессия Google Docs изменилась; повторите выпуск")
    if current.status != "ready":
        raise EditableDraftError("Изменения Google Docs ещё не синхронизированы")
    if (
        metadata.file_id != remote_file_id
        or metadata.edit_session_id != current.id
        or metadata.mime_type != DOCX_CONTENT_TYPE
    ):
        raise EditableDraftError("Файл Google Docs не совпадает с черновиком CRM")
    synchronized_revision = current.last_sync_remote_revision or current.remote_revision
    if metadata.revision != synchronized_revision:
        current.remote_revision = metadata.revision
        current.remote_modified_at = metadata.modified_at
        current.status = "changed"
        current.detail = "В Google Docs есть несинхронизированные изменения"
        session.add(current)
        await session.commit()
        raise EditableDraftError(current.detail)
    current.remote_modified_at = metadata.modified_at
    current.detail = None
    session.add(current)
    await session.commit()
    return str(synchronized_revision)


async def _scoped_edit_session(
    session: AsyncSession,
    *,
    tenant_scope: TenantScope,
    document_id: int,
    lock: bool,
) -> DocumentExternalEditSession | None:
    statement = (
        select(DocumentExternalEditSession)
        .join(
            DocumentArtifact,
            DocumentArtifact.id == DocumentExternalEditSession.document_artifact_id,
        )
        .join(OrderDocument, OrderDocument.id == DocumentArtifact.order_document_id)
        .join(Order, Order.id == OrderDocument.order_id)
        .where(
            DocumentExternalEditSession.tenant_id == tenant_scope.tenant_id,
            DocumentExternalEditSession.subject_type == "document_artifact",
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
