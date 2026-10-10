from __future__ import annotations

from urllib.parse import quote

from pydantic import ValidationError

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.security import AuthenticatedUser, require_manager_access
from modules.documents.application.errors import (
    ManagedDocumentConflictError,
    ManagedDocumentError,
    ManagedDocumentGenerationError,
    ManagedDocumentNotFoundError,
)
from modules.documents.application.lifecycle_service import (
    ManagedDocumentService,
)
from modules.documents.application.draft_preview import (
    ManagedDocumentDraftPreviewService,
)
from modules.documents.application.editable_draft import EditableDraftError
from modules.documents.application.artifact_helpers import (
    requires_guarded_draft_download,
    prepare_artifact_download,
)
from modules.documents.application.editable_draft_issue import (
    verify_document_external_edit_before_issue,
)
from modules.documents.infrastructure.artifact_storage import (
    PrivateDocumentArtifactStorage,
)
from modules.documents.infrastructure.template_source_storage import (
    PrivateTemplateSourceStorage,
)
from routers.manager_operation_ids import (
    CREATE_MANAGER_MANAGED_DOCUMENT_DRAFT,
    DELETE_MANAGER_MANAGED_DOCUMENT_DRAFT,
    DOWNLOAD_MANAGER_DOCUMENT_ARTIFACT,
    GET_MANAGER_DOCUMENT_ARTIFACT_ACCESS,
    ISSUE_MANAGER_MANAGED_DOCUMENT,
    LIST_MANAGER_DOCUMENT_ARTIFACTS,
    LIST_MANAGER_MANAGED_ORDER_DOCUMENTS,
    PREVIEW_MANAGER_MANAGED_DOCUMENT_DRAFT,
    VOID_MANAGER_MANAGED_DOCUMENT,
)
from routers.manager_permission_policy import ManagerPermissionRoute

from .draft_selection import selection_from_payload

from .schemas import (
    ManagedDocumentArtifactAccessResponse,
    ManagedDocumentArtifactItem,
    ManagedDocumentArtifactListResponse,
    ManagedDocumentDraftPayload,
    DocumentCustomerReadiness,
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
    "/documents/{document_id}/preview",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    operation_id=PREVIEW_MANAGER_MANAGED_DOCUMENT_DRAFT,
)
async def preview_managed_document_draft(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> Response:
    """
    Render a private/no-store PDF preview for a scoped managed draft using its saved
    context/template or edited source. Does not issue the document or reserve a number.
    Missing/inaccessible document returns 404, incompatible draft state 409 and
    rendering/source failure 503. See the [document lifecycle
    contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    private = _legacy_private_storage()
    try:
        content, filename = await ManagedDocumentDraftPreviewService.render_pdf(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            template_storage=PrivateTemplateSourceStorage(private),
            artifact_storage=PrivateDocumentArtifactStorage(private),
            pdf_converter=_legacy_pdf_converter(),
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404,
            PREVIEW_MANAGER_MANAGED_DOCUMENT_DRAFT,
            "managed_document_not_found",
            exc,
        )
    except ManagedDocumentConflictError as exc:
        raise _document_error(
            409,
            PREVIEW_MANAGER_MANAGED_DOCUMENT_DRAFT,
            "managed_document_preview_conflict",
            exc,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise _document_error(
            503,
            PREVIEW_MANAGER_MANAGED_DOCUMENT_DRAFT,
            "managed_document_preview_failed",
            exc,
        )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
        },
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
    """
    List documents for an order accessible in the current tenant/storefront, with
    lifecycle/provider metadata and accessible native artifacts. Missing order returns 404.
    Reading legacy metadata does not migrate or regenerate legacy files. See the [document
    lifecycle
    contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Create a native draft and immutable context snapshot for the current tenant/storefront
    order, selected proposal, issuer and document basis. Closed orders or incompatible
    template/replacement context return 409; missing dependencies 404, invalid selection 400
    and unavailable template storage 503. No official number is reserved yet. Repeating POST
    creates another draft; no caller idempotency receipt is provided. See the [document
    lifecycle
    contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        row = await ManagedDocumentService.create_draft(
            session,
            tenant_scope=auth.tenant_scope(),
            selection=selection_from_payload(order_id, payload),
            template_id=payload.template_id,
            replaces_document_id=payload.replaces_document_id,
            allow_incomplete_customer=payload.allow_incomplete_customer,
            template_storage=PrivateTemplateSourceStorage(_legacy_private_storage()),
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
    except OSError as exc:
        raise _document_error(
            503,
            CREATE_MANAGER_MANAGED_DOCUMENT_DRAFT,
            "managed_document_template_unavailable",
            ValueError("Не удалось прочитать шаблон документа"),
        ) from exc
    except (ManagedDocumentError, TypeError, ValueError) as exc:
        raise _document_error(
            400, CREATE_MANAGER_MANAGED_DOCUMENT_DRAFT, "managed_document_invalid", exc
        )
    return await _document_item(session, auth, row)


@router.delete(
    "/documents/{document_id}/draft",
    status_code=204,
    operation_id=DELETE_MANAGER_MANAGED_DOCUMENT_DRAFT,
)
async def delete_managed_document_draft(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> Response:
    """
    Delete a scoped unissued native draft, its working DOCX registry and editor sessions,
    returning 204. Reserved numbers, issued artifacts or closed orders prevent deletion
    (409); missing document
    returns 404. Use lifecycle commands for issued records, not this endpoint. A repeat
    after deletion returns 404. Existing remote Google copies remain in Drive.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        await ManagedDocumentService.delete_draft(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404,
            DELETE_MANAGER_MANAGED_DOCUMENT_DRAFT,
            "managed_document_not_found",
            exc,
        )
    except ManagedDocumentConflictError as exc:
        raise _document_error(
            409,
            DELETE_MANAGER_MANAGED_DOCUMENT_DRAFT,
            "managed_document_immutable",
            exc,
        )
    return Response(status_code=204)


@router.post(
    "/documents/{document_id}/issue",
    response_model=ManagedDocumentItem,
    operation_id=ISSUE_MANAGER_MANAGED_DOCUMENT,
)
async def issue_managed_document(
    document_id: int,
    participant_statement_confirmed: bool = False,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
) -> ManagedDocumentItem:
    """
    Issue a current-tenant managed draft by reserving its official number and rendering
    immutable DOCX/PDF artifacts. Participant statements require explicit factual
    confirmation of the current text using participant_statement_confirmed=true;
    the issuing actor, timestamp and exact artifact checksums are frozen in the snapshot.
    Saved external edits must be synchronized and their remote
    revision verified first. Missing document returns 404, state/edit conflicts 409 and
    generation failure 503. A failed render retains its reservation; retry the same document
    rather than creating a new draft. Already issued/sent/signed records reuse their
    issuance result. See the [document lifecycle
    contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    private = _legacy_private_storage()
    try:
        # Check the actual saved snapshot/template before any external edit-provider call.
        await ManagedDocumentService.validate_issue_customer_readiness(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            template_storage=PrivateTemplateSourceStorage(private),
            participant_statement_confirmed=participant_statement_confirmed,
        )
        from .router import get_google_document_edit_provider

        provider = None
        try:
            provider = await get_google_document_edit_provider(
                session=session,
                tenant_scope=auth.tenant_scope(),
            )
        except Exception:
            # The verifier permits no-provider issuance only when this draft has
            # never been sent to an external editor.
            provider = None
        verified_remote_revision = await verify_document_external_edit_before_issue(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            provider=provider,
        )
        result = await ManagedDocumentService.issue(
            session,
            tenant_scope=auth.tenant_scope(),
            document_id=document_id,
            template_storage=PrivateTemplateSourceStorage(private),
            artifact_storage=PrivateDocumentArtifactStorage(private),
            pdf_converter=_legacy_pdf_converter(),
            verified_remote_revision=verified_remote_revision,
            participant_statement_confirmed=participant_statement_confirmed,
            participant_statement_confirmed_by=auth.username,
        )
    except ManagedDocumentNotFoundError as exc:
        raise _document_error(
            404, ISSUE_MANAGER_MANAGED_DOCUMENT, "managed_document_not_found", exc
        )
    except (ManagedDocumentConflictError, EditableDraftError) as exc:
        raise _document_error(
            409, ISSUE_MANAGER_MANAGED_DOCUMENT, "managed_document_conflict", exc
        )
    except OSError as exc:
        raise _document_error(
            503,
            ISSUE_MANAGER_MANAGED_DOCUMENT,
            "managed_document_template_unavailable",
            exc,
        )
    except (TypeError, ValueError) as exc:
        raise _document_error(
            409,
            ISSUE_MANAGER_MANAGED_DOCUMENT,
            "managed_document_snapshot_invalid",
            exc,
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
    """
    Void a scoped managed document with an explicit reason and mark its numbering
    reservation void. Artifacts and official number are retained; voiding does not delete or
    recycle them. Missing document returns 404, forbidden lifecycle transition or invalid
    reason 409. See the [document lifecycle
    contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    List private artifact metadata for a document accessible in the current
    tenant/storefront. Missing document returns 404. This does not return artifact bytes or
    provide a public media URL.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Resolve private access to a scoped artifact. Returns a provider signed URL for a bounded
    TTL of 30–3600 seconds, or the authenticated API download path when signing is
    unavailable. Missing artifact/file returns 404 and integrity failure 409. The fallback
    path still requires Manager authentication; expires_in is not an anonymous access grant.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
        if await requires_guarded_draft_download(
            session, tenant_scope=auth.tenant_scope(), artifact=artifact
        ):
            url = None
        else:
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
    except OSError as exc:
        raise _document_error(
            503,
            GET_MANAGER_DOCUMENT_ARTIFACT_ACCESS,
            "document_artifact_unavailable",
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
    """
    Download bytes of a scoped private artifact after storage integrity validation. Missing
    artifact/file returns 404 and corrupt/incompatible storage metadata 409. Response is an
    attachment with its artifact content type and private/no-store headers. Read-only access
    remains separate from issuance.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
        content = await prepare_artifact_download(
            session,
            tenant_scope=auth.tenant_scope(),
            artifact=artifact,
            content=content,
            template_storage=PrivateTemplateSourceStorage(_legacy_private_storage()),
        )
    except (ManagedDocumentNotFoundError, FileNotFoundError) as exc:
        raise _document_error(
            404, DOWNLOAD_MANAGER_DOCUMENT_ARTIFACT, "document_artifact_not_found", exc
        )
    except OSError as exc:
        raise _document_error(
            503,
            DOWNLOAD_MANAGER_DOCUMENT_ARTIFACT,
            "document_artifact_unavailable",
            exc,
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
        official_full_number = str(
            ((document.render_snapshot or {}).get("values") or {}).get(
                "document.official_full_number", ""
            )
            or f"{document.official_series or ''}{document.official_number}"
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
    statement_values = ((document.render_snapshot or {}).get("values") or {})
    return ManagedDocumentItem(
        participant_statement=(
            {name: statement_values.get(f"participant.{name}", "") for name in
             ("procedure_reference", "lot", "buyer_name", "declaration_text")}
            if document.doc_type == "participant_statement" else None
        ),
        maintenance_source_order_id=(
            (document.render_snapshot or {})
            .get("meta", {})
            .get("maintenance", {})
            .get("source_order_id")
        ),
        id=document.id,
        order_id=document.order_id,
        legal_entity_id=document.legal_entity_id,
        proposal_id=document.proposal_id,
        doc_type=document.doc_type,
        business_role=document.business_role,
        document_role_type=((document.render_snapshot or {}).get("meta") or {}).get(
            "document_role_type"
        ),
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
        customer_readiness=_cached_customer_readiness(document),
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


def _cached_customer_readiness(document):
    meta = (document.render_snapshot or {}).get("meta") or {}
    if not isinstance(meta, dict):
        return None
    try:
        return DocumentCustomerReadiness.model_validate(meta.get("customer_readiness"))
    except ValidationError:
        return None
