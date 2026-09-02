from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.request_context import current_request_id
from models import DocumentExternalEditSession, TenantAuditEvent
from models.tenancy import TenantScope
from modules.documents.infrastructure.external_edit_provider import (
    DOCX_CONTENT_TYPE,
    DownloadedExternalEditFile,
    ExternalEditFileMetadata,
)


EXTERNAL_EDIT_LEASE_TTL = timedelta(minutes=5)


def sync_request_fingerprint(
    *, base_checksum_sha256: str, remote_revision: str
) -> str:
    canonical = json.dumps(
        [
            "document-external-edit-sync-v1",
            str(base_checksum_sha256).strip().lower(),
            str(remote_revision).strip(),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def external_edit_lease_is_live(
    edit_session: DocumentExternalEditSession,
) -> bool:
    if edit_session.status != "syncing" or not edit_session.active_sync_key:
        return False
    updated_at = edit_session.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return updated_at > utc_now() - EXTERNAL_EDIT_LEASE_TTL


def validate_external_docx_metadata(
    metadata: ExternalEditFileMetadata,
    *,
    expected_file_id: str | None = None,
    expected_edit_session_id: str | None = None,
) -> None:
    if not isinstance(metadata, ExternalEditFileMetadata):
        raise TypeError("Provider returned invalid file metadata")
    file_id = _required_metadata_text(metadata.file_id, "ID файла", 500)
    if expected_file_id is not None and file_id != expected_file_id:
        raise ValueError("Provider returned another file")
    edit_session_id = _required_metadata_text(
        metadata.edit_session_id, "Сессия файла", 160
    )
    if (
        expected_edit_session_id is not None
        and edit_session_id != expected_edit_session_id
    ):
        raise ValueError("Provider file belongs to another edit session")
    _required_metadata_text(metadata.edit_url, "Ссылка редактора", 2000)
    filename = _required_metadata_text(metadata.filename, "Имя файла", 255)
    if not filename.lower().endswith(".docx"):
        raise ValueError("Provider file must preserve the DOCX extension")
    if metadata.mime_type != DOCX_CONTENT_TYPE:
        raise ValueError("Provider file must preserve the DOCX MIME type")
    _required_metadata_text(metadata.revision, "Версия файла", 500)


def validate_external_docx_download(
    downloaded: DownloadedExternalEditFile,
    *,
    expected_file_id: str,
    expected_edit_session_id: str,
    max_bytes: int,
) -> None:
    if not isinstance(downloaded, DownloadedExternalEditFile):
        raise TypeError("Provider returned an invalid DOCX download")
    validate_external_docx_metadata(
        downloaded.metadata,
        expected_file_id=expected_file_id,
        expected_edit_session_id=expected_edit_session_id,
    )
    if not isinstance(downloaded.content, bytes) or not downloaded.content:
        raise ValueError("Provider returned an empty DOCX")
    if len(downloaded.content) > max_bytes:
        raise ValueError("Provider DOCX exceeds the allowed size")


def _required_metadata_text(value: object, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{label} имеет неверный формат")
    return normalized


def add_external_edit_sync_audit(
    session: AsyncSession,
    *,
    tenant_scope: TenantScope,
    edit_session: DocumentExternalEditSession,
    actor_staff_user_id: int | None,
    actor_username: str | None,
    action: str,
    entity_type: str,
    entity_id: int,
    change_set: dict[str, object] | None = None,
) -> None:
    """Stage one append-only audit event in the successful sync transaction."""

    if not actor_username:
        return
    audit_change_set: dict[str, object] = {
        "external_edit_session_id": edit_session.id,
        "provider": edit_session.provider,
        "remote_revision": edit_session.last_sync_remote_revision,
    }
    audit_change_set.update(change_set or {})
    session.add(
        TenantAuditEvent(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            actor_staff_user_id=actor_staff_user_id,
            actor_username=actor_username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=current_request_id(),
            change_set=audit_change_set,
        )
    )


async def claim_remote_initialization(
    session: AsyncSession,
    edit_session: DocumentExternalEditSession,
    *,
    conflict_error: type[Exception],
) -> tuple[DocumentExternalEditSession, str | None]:
    """Claim one remote-file initialization across tabs and API workers."""

    current = await _locked_session(
        session,
        tenant_id=edit_session.tenant_id,
        edit_session_id=edit_session.id,
    )
    if current is None:
        raise conflict_error("Сессия онлайн-редактора больше недоступна")
    if current.remote_file_id:
        return current, None
    if external_edit_lease_is_live(current):
        raise conflict_error("Файл уже подготавливается в другой вкладке")
    claim_key = f"init:{secrets.token_hex(16)}"
    current.status = "syncing"
    current.active_sync_key = claim_key
    current.active_sync_fingerprint = None
    current.detail = None
    current.updated_at = utc_now()
    session.add(current)
    await session.commit()
    return current, claim_key


async def lock_remote_initialization_result(
    session: AsyncSession,
    edit_session: DocumentExternalEditSession,
    *,
    claim_key: str,
    conflict_error: type[Exception],
) -> DocumentExternalEditSession:
    current = await _locked_session(
        session,
        tenant_id=edit_session.tenant_id,
        edit_session_id=edit_session.id,
    )
    if current is None or current.active_sync_key != claim_key:
        raise conflict_error("Сессия онлайн-редактора изменилась параллельно")
    return current


async def record_external_edit_error(
    session: AsyncSession,
    edit_session: DocumentExternalEditSession,
) -> None:
    expected_sync_key = edit_session.active_sync_key
    had_remote_file = bool(edit_session.remote_file_id)
    current = await _locked_session(
        session,
        tenant_id=edit_session.tenant_id,
        edit_session_id=edit_session.id,
    )
    if current is None:
        return
    if expected_sync_key is not None and current.active_sync_key != expected_sync_key:
        return
    if (
        expected_sync_key is None
        and had_remote_file
        and external_edit_lease_is_live(current)
    ):
        return
    current.status = "error"
    current.detail = "Онлайн-редактор не смог завершить операцию"
    current.active_sync_key = None
    current.active_sync_fingerprint = None
    current.updated_at = utc_now()
    session.add(current)
    await session.commit()


async def _locked_session(
    session: AsyncSession,
    *,
    tenant_id: int,
    edit_session_id: str,
) -> DocumentExternalEditSession | None:
    return (
        await session.execute(
            select(DocumentExternalEditSession)
            .where(
                DocumentExternalEditSession.id == edit_session_id,
                DocumentExternalEditSession.tenant_id == tenant_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
