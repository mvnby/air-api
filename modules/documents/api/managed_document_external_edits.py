from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.errors import (
    ManagedDocumentConflictError,
    ManagedDocumentNotFoundError,
)
from modules.documents.application.external_edit_sessions import (
    ExternalEditProviderError,
    ExternalEditSessionConflictError,
    ExternalEditSessionNotFoundError,
)
from modules.documents.application.managed_document_external_edits import (
    ManagedDocumentExternalEditSessionService,
)
from modules.documents.infrastructure.artifact_storage import (
    PrivateDocumentArtifactStorage,
)
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from routers.manager_operation_ids import (
    CREATE_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
    GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
    SYNC_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from services.document_drive_contracts import DocumentDriveConnectionError

from .external_edit_schemas import ExternalEditSessionItem, TemplateExternalEditSyncPayload


router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/documents/{document_id}/google-edit-session",
    response_model=ExternalEditSessionItem,
    operation_id=GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
)
async def get_managed_document_google_edit_session(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ExternalEditSessionItem:
    provider = await _provider(session, auth)
    try:
        row = await ManagedDocumentExternalEditSessionService.get_session(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            provider=provider,
        )
    except ManagedDocumentNotFoundError as exc:
        raise _error(404, GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_not_found", exc)
    except ExternalEditSessionNotFoundError as exc:
        raise _error(404, GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_edit_session_not_found", exc)
    except (ManagedDocumentConflictError, ExternalEditSessionConflictError) as exc:
        raise _error(409, GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_edit_conflict", exc)
    except ExternalEditProviderError as exc:
        raise _error(502, GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_provider_failed", exc)
    return _item(row)


@router.post(
    "/documents/{document_id}/google-edit-session",
    response_model=ExternalEditSessionItem,
    operation_id=CREATE_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
)
async def create_managed_document_google_edit_session(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ExternalEditSessionItem:
    provider = await _provider(session, auth)
    private = _private_storage()
    try:
        row = await ManagedDocumentExternalEditSessionService.ensure_session(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            template_storage=PrivateTemplateSourceStorage(private),
            artifact_storage=PrivateDocumentArtifactStorage(private),
            provider=provider,
            staff_user_id=auth.staff_user_id,
        )
    except ManagedDocumentNotFoundError as exc:
        raise _error(404, CREATE_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_not_found", exc)
    except (ManagedDocumentConflictError, ExternalEditSessionConflictError) as exc:
        raise _error(409, CREATE_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_edit_conflict", exc)
    except ExternalEditProviderError as exc:
        raise _error(502, CREATE_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_provider_failed", exc)
    except (ValueError, TypeError) as exc:
        raise _error(400, CREATE_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_edit_invalid", exc)
    return _item(row)


@router.post(
    "/documents/{document_id}/google-edit-session/sync",
    response_model=ExternalEditSessionItem,
    operation_id=SYNC_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
)
async def sync_managed_document_google_edit_session(
    document_id: int,
    payload: TemplateExternalEditSyncPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ExternalEditSessionItem:
    provider = await _provider(session, auth)
    try:
        row = await ManagedDocumentExternalEditSessionService.sync(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            expected_base_checksum_sha256=payload.expected_base_checksum_sha256,
            expected_remote_revision=payload.expected_remote_revision,
            idempotency_key=payload.idempotency_key,
            artifact_storage=PrivateDocumentArtifactStorage(_private_storage()),
            provider=provider,
            staff_user_id=auth.staff_user_id,
            actor_username=auth.username,
        )
    except (ManagedDocumentNotFoundError, ExternalEditSessionNotFoundError) as exc:
        raise _error(404, SYNC_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_edit_session_not_found", exc)
    except (ManagedDocumentConflictError, ExternalEditSessionConflictError) as exc:
        raise _error(409, SYNC_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_sync_conflict", exc)
    except ExternalEditProviderError as exc:
        raise _error(502, SYNC_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_provider_failed", exc)
    except (ValueError, TypeError) as exc:
        raise _error(400, SYNC_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION, "managed_document_google_sync_invalid", exc)
    return _item(row)


async def _provider(session: AsyncSession, auth: AuthenticatedUser):
    from .router import get_google_document_edit_provider

    try:
        return await get_google_document_edit_provider(
            session=session,
            tenant_scope=auth.tenant_scope(),
        )
    except DocumentDriveConnectionError as exc:
        raise _error(
            exc.status_code,
            GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
            exc.code,
            exc,
        ) from exc
    except Exception as exc:
        raise _error(
            503,
            GET_MANAGER_MANAGED_DOCUMENT_GOOGLE_EDIT_SESSION,
            "google_drive_runtime_unavailable",
            RuntimeError("Подключение Google Диска временно недоступно"),
        ) from exc


def _private_storage():
    from .router import get_private_attachment_storage

    return get_private_attachment_storage()


def _item(row) -> ExternalEditSessionItem:
    return ExternalEditSessionItem(
        id=row.id,
        status=row.status,
        edit_url=row.edit_url,
        can_edit=bool(row.edit_url and row.status != "error"),
        base_checksum_sha256=row.base_checksum_sha256,
        remote_revision=row.remote_revision,
        modified_at=row.remote_modified_at,
        last_synced_at=row.last_synced_at,
        detail=row.detail,
    )


def _error(status_code: int, endpoint: str, code: str, exc: Exception):
    return manager_http_error(
        status_code=status_code,
        endpoint=endpoint,
        error_code=code,
        message=str(exc),
    )
