from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.context_builder import DocumentContextSelection
from modules.documents.domain import ConsumerDocumentTerms
from modules.documents.application.errors import (
    ManagedDocumentConflictError,
    ManagedDocumentError,
    ManagedDocumentGenerationError,
    ManagedDocumentNotFoundError,
)
from modules.documents.application.lifecycle_service import (
    ManagedDocumentService,
)
from modules.documents.infrastructure.artifact_storage import (
    PrivateDocumentArtifactStorage,
)
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from routers.manager_operation_ids import (
    CREATE_MANAGER_MANAGED_DOCUMENT_DRAFT,
    DOWNLOAD_MANAGER_DOCUMENT_ARTIFACT,
    GET_MANAGER_DOCUMENT_ARTIFACT_ACCESS,
    ISSUE_MANAGER_MANAGED_DOCUMENT,
    LIST_MANAGER_DOCUMENT_ARTIFACTS,
    LIST_MANAGER_MANAGED_ORDER_DOCUMENTS,
    VOID_MANAGER_MANAGED_DOCUMENT,
)
from routers.manager_permission_policy import ManagerPermissionRoute

from .schemas import (
    ManagedDocumentArtifactAccessResponse,
    ManagedDocumentArtifactItem,
    ManagedDocumentArtifactListResponse,
    ManagedDocumentDraftPayload,
    ManagedDocumentItem,
    ManagedDocumentListResponse,
    ManagedDocumentVoidPayload,
)


router = APIRouter(
    prefix="/api/manager/document-system",
    tags=["manager-document-system"],
    dependencies=[Depends(require_manager_access)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/orders/{order_id}/documents",
    response_model=ManagedDocumentListResponse,
    operation_id=LIST_MANAGER_MANAGED_ORDER_DOCUMENTS,
)
async def list_managed_order_documents(
    order_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ManagedDocumentListResponse:
    try:
        rows = await ManagedDocumentService.list_for_order(
            session,
            tenant_scope=auth.tenant_scope(),
            order_id=order_id,
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404, LIST_MANAGER_MANAGED_ORDER_DOCUMENTS, "order_not_found", exc
        )
    return ManagedDocumentListResponse(
        items=[await _document_item(session, auth, row) for row in rows]
    )


@router.post(
    "/orders/{order_id}/documents/drafts",
    response_model=ManagedDocumentItem,
    operation_id=CREATE_MANAGER_MANAGED_DOCUMENT_DRAFT,
)
async def create_managed_document_draft(
    order_id: int,
    payload: ManagedDocumentDraftPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ManagedDocumentItem:
    try:
        row = await ManagedDocumentService.create_draft(
            session,
            tenant_scope=auth.tenant_scope(),
            selection=DocumentContextSelection(
                order_id=order_id,
                document_type=payload.document_type,
                legal_entity_id=payload.legal_entity_id,
                issue_date=payload.issue_date,
                issue_city=payload.issue_city,
                proposal_id=payload.proposal_id,
                base_document_id=payload.base_document_id,
                base_customer_contract_id=payload.base_customer_contract_id,
                scope_customer_branch_id=payload.scope_customer_branch_id,
                scope_title=payload.scope_title,
                scope_address=payload.scope_address,
                scope_service_line_ids=tuple(payload.scope_service_line_ids),
                scope_service_line_quantities=payload.scope_service_line_quantities,
                scope_product_line_ids=tuple(payload.scope_product_line_ids),
                business_role=payload.business_role,
                consumer_terms=(
                    ConsumerDocumentTerms(**payload.consumer_terms.model_dump())
                    if payload.consumer_terms is not None
                    else None
                ),
            ),
            template_id=payload.template_id,
            replaces_document_id=payload.replaces_document_id,
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404,
            CREATE_MANAGER_MANAGED_DOCUMENT_DRAFT,
            "managed_document_dependency_not_found",
            exc,
        )
    except ManagedDocumentConflictError as exc:
        raise _document_error(
            409, CREATE_MANAGER_MANAGED_DOCUMENT_DRAFT, "managed_document_conflict", exc
        )
    except (ManagedDocumentError, ValueError) as exc:
        raise _document_error(
            400, CREATE_MANAGER_MANAGED_DOCUMENT_DRAFT, "managed_document_invalid", exc
        )
    return await _document_item(session, auth, row)


@router.post(
    "/documents/{document_id}/issue",
    response_model=ManagedDocumentItem,
    operation_id=ISSUE_MANAGER_MANAGED_DOCUMENT,
)
async def issue_managed_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ManagedDocumentItem:
    private = _legacy_private_storage()
    try:
        result = await ManagedDocumentService.issue(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            template_storage=PrivateTemplateSourceStorage(private),
            artifact_storage=PrivateDocumentArtifactStorage(private),
            pdf_converter=_legacy_pdf_converter(),
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404, ISSUE_MANAGER_MANAGED_DOCUMENT, "managed_document_not_found", exc
        )
    except ManagedDocumentConflictError as exc:
        raise _document_error(
            409, ISSUE_MANAGER_MANAGED_DOCUMENT, "managed_document_conflict", exc
        )
    except ManagedDocumentGenerationError as exc:
        raise _document_error(
            503,
            ISSUE_MANAGER_MANAGED_DOCUMENT,
            "managed_document_generation_failed",
            exc,
        )
    return _document_item_from_parts(result.document, list(result.artifacts))


@router.post(
    "/documents/{document_id}/void",
    response_model=ManagedDocumentItem,
    operation_id=VOID_MANAGER_MANAGED_DOCUMENT,
)
async def void_managed_document(
    document_id: int,
    payload: ManagedDocumentVoidPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ManagedDocumentItem:
    try:
        row = await ManagedDocumentService.void(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            reason=payload.reason,
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404, VOID_MANAGER_MANAGED_DOCUMENT, "managed_document_not_found", exc
        )
    except (ManagedDocumentConflictError, ValueError) as exc:
        raise _document_error(
            409, VOID_MANAGER_MANAGED_DOCUMENT, "managed_document_conflict", exc
        )
    return await _document_item(session, auth, row)


@router.get(
    "/documents/{document_id}/artifacts",
    response_model=ManagedDocumentArtifactListResponse,
    operation_id=LIST_MANAGER_DOCUMENT_ARTIFACTS,
)
async def list_document_artifacts(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ManagedDocumentArtifactListResponse:
    try:
        rows = await ManagedDocumentService.list_artifacts(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404, LIST_MANAGER_DOCUMENT_ARTIFACTS, "managed_document_not_found", exc
        )
    return ManagedDocumentArtifactListResponse(
        items=[ManagedDocumentArtifactItem.model_validate(row) for row in rows]
    )


@router.get(
    "/artifacts/{artifact_id}/access",
    response_model=ManagedDocumentArtifactAccessResponse,
    operation_id=GET_MANAGER_DOCUMENT_ARTIFACT_ACCESS,
)
async def get_document_artifact_access(
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ManagedDocumentArtifactAccessResponse:
    try:
        artifact = await ManagedDocumentService.get_artifact(
            session,
            tenant_scope=auth.tenant_scope(),
            artifact_id=artifact_id,
        )
        ttl = max(30, min(int(settings.SERVICE_ATTACHMENT_ACCESS_TTL_SECONDS), 3600))
        storage = PrivateDocumentArtifactStorage(
            _legacy_private_storage(artifact.provider)
        )
        url = await storage.presign(
            ManagedDocumentService.stored_artifact(artifact),
            expires_seconds=ttl,
        )
    except (ManagedDocumentNotFoundError, FileNotFoundError) as exc:
        raise _document_error(
            404,
            GET_MANAGER_DOCUMENT_ARTIFACT_ACCESS,
            "document_artifact_not_found",
            exc,
        )
    except (TypeError, ValueError):
        raise manager_http_error(
            status_code=409,
            endpoint=GET_MANAGER_DOCUMENT_ARTIFACT_ACCESS,
            error_code="document_artifact_integrity_failed",
            message="Файл документа поврежден или недоступен",
        )
    if not url:
        url = f"/api/manager/document-system/artifacts/{artifact.id}/download"
    return ManagedDocumentArtifactAccessResponse(url=url, expires_in=ttl)


@router.get(
    "/artifacts/{artifact_id}/download",
    operation_id=DOWNLOAD_MANAGER_DOCUMENT_ARTIFACT,
)
async def download_document_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> Response:
    try:
        artifact = await ManagedDocumentService.get_artifact(
            session,
            tenant_scope=auth.tenant_scope(),
            artifact_id=artifact_id,
        )
        storage = PrivateDocumentArtifactStorage(
            _legacy_private_storage(artifact.provider)
        )
        content = await storage.read(ManagedDocumentService.stored_artifact(artifact))
    except (ManagedDocumentNotFoundError, FileNotFoundError) as exc:
        raise _document_error(
            404, DOWNLOAD_MANAGER_DOCUMENT_ARTIFACT, "document_artifact_not_found", exc
        )
    except (TypeError, ValueError):
        raise manager_http_error(
            status_code=409,
            endpoint=DOWNLOAD_MANAGER_DOCUMENT_ARTIFACT,
            error_code="document_artifact_integrity_failed",
            message="Файл документа поврежден или недоступен",
        )
    return Response(
        content=content,
        media_type=artifact.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(artifact.filename)}",
        },
    )


def _legacy_private_storage(provider: str | None = None):
    """Resolve through the compatibility module so legacy test patches work."""
    from .router import get_private_attachment_storage

    return get_private_attachment_storage(provider)


def _legacy_pdf_converter():
    from .router import _pdf_converter

    return _pdf_converter()


async def _document_item(
    session: AsyncSession,
    auth: AuthenticatedUser,
    document,
) -> ManagedDocumentItem:
    artifacts = []
    if document.tenant_id == auth.tenant_id:
        artifacts = await ManagedDocumentService.list_artifacts(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document.id,
        )
    return _document_item_from_parts(document, artifacts)


def _document_item_from_parts(document, artifacts) -> ManagedDocumentItem:
    official_full_number = None
    if document.official_number:
        official_full_number = (
            f"{document.official_series or ''}{document.official_number}"
        )
    provider = (
        "native"
        if document.template_version_id or artifacts
        else (
            "google"
            if document.google_file_id or document.google_edit_url
            else "external"
        )
    )
    return ManagedDocumentItem(
        id=document.id,
        order_id=document.order_id,
        legal_entity_id=document.legal_entity_id,
        proposal_id=document.proposal_id,
        doc_type=document.doc_type,
        business_role=document.business_role,
        status=document.status or "issued",
        provider=provider,
        internal_reference=document.internal_reference,
        official_series=document.official_series,
        official_period_key=document.official_period_key,
        official_number=document.official_number,
        official_full_number=official_full_number,
        official_date=document.official_date,
        issue_city=str(
            ((document.render_snapshot or {}).get("values") or {}).get(
                "document.issue_city", ""
            )
            or ""
        )
        or None,
        display_number=official_full_number or document.number,
        date=document.date,
        document_template_id=document.document_template_id,
        template_version_id=document.template_version_id,
        base_document_id=document.base_document_id,
        base_customer_contract_id=document.base_customer_contract_id,
        replaces_document_id=document.replaces_document_id,
        issued_at=document.issued_at,
        sent_at=document.sent_at,
        signed_at=document.signed_at,
        voided_at=document.voided_at,
        void_reason=document.void_reason,
        google_edit_url=document.google_edit_url,
        created_at=document.created_at,
        artifacts=[
            ManagedDocumentArtifactItem.model_validate(item) for item in artifacts
        ],
    )


def _document_error(status_code: int, endpoint: str, code: str, exc: Exception):
    return manager_http_error(
        status_code=status_code,
        endpoint=endpoint,
        error_code=code,
        message=str(exc),
    )
