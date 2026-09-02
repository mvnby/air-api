from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.external_edit_sessions import (
    ExternalEditProviderError,
    ExternalEditSessionConflictError,
    ExternalEditSessionError,
    ExternalEditSessionNotFoundError,
    TemplateExternalEditSessionService,
)
from modules.documents.application.template_versions import (
    TemplateVersionConflictError,
    TemplateVersionError,
    TemplateVersionNotFoundError,
    TemplateVersionValidationError,
)
from modules.documents.infrastructure.external_edit_provider import ExternalEditProvider
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from routers.manager_operation_ids import (
    CREATE_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
    GET_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
    SYNC_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from services.document_drive_contracts import DocumentDriveConnectionError

from .external_edit_schemas import (
    ExternalEditSessionItem,
    TemplateExternalEditSyncPayload,
    TemplateExternalEditSyncResponse,
)
from .schemas import NativeTemplateVersionItem


router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/templates/{template_id}/versions/{version_id}/google-edit-session",
    response_model=ExternalEditSessionItem,
    operation_id=GET_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
)
async def get_native_template_google_edit_session(
    template_id: int,
    version_id: int,
    legal_entity_id: int = Query(..., gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ExternalEditSessionItem:
    provider = await _google_provider(
        session, auth, endpoint=GET_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION
    )
    try:
        row = await TemplateExternalEditSessionService.get_session(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
            provider=provider,
        )
    except ExternalEditSessionNotFoundError as exc:
        raise _edit_error(
            404,
            GET_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_edit_session_not_found",
            exc,
        )
    except ExternalEditSessionConflictError as exc:
        raise _edit_error(
            409,
            GET_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_edit_session_conflict",
            exc,
        )
    except ExternalEditProviderError as exc:
        raise _edit_error(
            502,
            GET_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_provider_failed",
            exc,
        )
    return _session_item(row)


@router.post(
    "/templates/{template_id}/versions/{version_id}/google-edit-session",
    response_model=ExternalEditSessionItem,
    operation_id=CREATE_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
)
async def create_native_template_google_edit_session(
    template_id: int,
    version_id: int,
    legal_entity_id: int = Query(..., gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ExternalEditSessionItem:
    provider = await _google_provider(
        session, auth, endpoint=CREATE_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION
    )
    try:
        row = await TemplateExternalEditSessionService.ensure_session(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
            source_storage=PrivateTemplateSourceStorage(_private_storage()),
            provider=provider,
            staff_user_id=auth.staff_user_id,
        )
    except (TemplateVersionNotFoundError, ExternalEditSessionNotFoundError) as exc:
        raise _edit_error(
            404,
            CREATE_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_version_not_found",
            exc,
        )
    except (ExternalEditSessionConflictError, TemplateVersionConflictError) as exc:
        raise _edit_error(
            409,
            CREATE_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_edit_session_conflict",
            exc,
        )
    except ExternalEditProviderError as exc:
        raise _edit_error(
            502,
            CREATE_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_provider_failed",
            exc,
        )
    except (ExternalEditSessionError, TemplateVersionError, ValueError) as exc:
        raise _edit_error(
            400,
            CREATE_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_edit_session_invalid",
            exc,
        )
    return _session_item(row)


@router.post(
    "/templates/{template_id}/versions/{version_id}/google-edit-session/sync",
    response_model=TemplateExternalEditSyncResponse,
    operation_id=SYNC_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
)
async def sync_native_template_google_edit_session(
    template_id: int,
    version_id: int,
    payload: TemplateExternalEditSyncPayload,
    legal_entity_id: int = Query(..., gt=0),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> TemplateExternalEditSyncResponse:
    provider = await _google_provider(
        session, auth, endpoint=SYNC_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION
    )
    try:
        result = await TemplateExternalEditSessionService.sync(
            session,
            tenant_scope=auth.tenant_scope(),
            legal_entity_id=legal_entity_id,
            template_id=template_id,
            version_id=version_id,
            expected_base_checksum_sha256=payload.expected_base_checksum_sha256,
            expected_remote_revision=payload.expected_remote_revision,
            idempotency_key=payload.idempotency_key,
            source_storage=PrivateTemplateSourceStorage(_private_storage()),
            provider=provider,
            staff_user_id=auth.staff_user_id,
            actor_username=auth.username,
        )
    except (TemplateVersionNotFoundError, ExternalEditSessionNotFoundError) as exc:
        raise _edit_error(
            404,
            SYNC_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_edit_session_not_found",
            exc,
        )
    except (ExternalEditSessionConflictError, TemplateVersionConflictError) as exc:
        raise _edit_error(
            409,
            SYNC_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_sync_conflict",
            exc,
        )
    except TemplateVersionValidationError as exc:
        raise manager_http_error(
            status_code=422,
            endpoint=SYNC_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            error_code="native_template_google_validation_failed",
            message=str(exc),
            field_errors={
                f"{issue.location}:{index}": issue.message
                for index, issue in enumerate(exc.result.issues)
            },
        ) from exc
    except ExternalEditProviderError as exc:
        raise _edit_error(
            502,
            SYNC_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_provider_failed",
            exc,
        )
    except (ExternalEditSessionError, TemplateVersionError, ValueError) as exc:
        raise _edit_error(
            400,
            SYNC_MANAGER_NATIVE_TEMPLATE_GOOGLE_EDIT_SESSION,
            "native_template_google_sync_invalid",
            exc,
        )
    return TemplateExternalEditSyncResponse(
        session=_session_item(result.edit_session),
        new_template_version=(
            NativeTemplateVersionItem.model_validate(result.new_template_version)
            if result.new_template_version is not None
            else None
        ),
    )


async def _google_provider(
    session: AsyncSession, auth: AuthenticatedUser, *, endpoint: str
) -> ExternalEditProvider:
    """Resolve via the composition module so tests and auth adapters stay isolated."""

    from .router import get_google_document_edit_provider

    try:
        return await get_google_document_edit_provider(
            session=session,
            tenant_scope=auth.tenant_scope(),
        )
    except DocumentDriveConnectionError as exc:
        raise _edit_error(
            exc.status_code,
            endpoint,
            exc.code,
            exc,
        ) from exc
    except Exception as exc:
        raise _edit_error(
            503,
            endpoint,
            "google_drive_runtime_unavailable",
            RuntimeError("Подключение Google Диска временно недоступно"),
        ) from exc


def _private_storage():
    from .router import get_private_attachment_storage

    return get_private_attachment_storage()


def _session_item(row) -> ExternalEditSessionItem:
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


def _edit_error(status_code: int, endpoint: str, code: str, exc: Exception):
    return manager_http_error(
        status_code=status_code,
        endpoint=endpoint,
        error_code=code,
        message=str(exc),
    )
