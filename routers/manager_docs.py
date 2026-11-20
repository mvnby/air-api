import logging
from datetime import date, datetime
from pathlib import PurePath
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Header, Query
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import (
    BAD_REQUEST,
    CUSTOMER_NOT_FOUND,
    DOCUMENT_HAS_DEPENDENTS,
    DOCUMENT_MANAGED_BY_NATIVE,
    DOCUMENT_NOT_FOUND,
    ORDER_DOCUMENTS_LOCKED,
    ORDER_NOT_FOUND,
)
from core.security import (
    AuthenticatedUser,
    get_current_manager_tenant_scope,
    get_current_username,
    require_manager_access,
    require_system_manager_tenant_scope,
)
from models.tenancy import TenantScope
from modules.documents.application.external_order_documents import (
    ExternalDocumentFileRole, ExternalDocumentStatus, ExternalDocumentType, ExternalOrderDocumentService,
)
from routers.manager_external_document_actions import (
    attach_external_document, create_external_document, document_item, download_external_document,
)
from routers.manager_operation_ids import (
    GET_MANAGER_ORDER_DOCUMENTS,
    ATTACH_MANAGER_DOC_FILE,
    REGISTER_MANAGER_EXTERNAL_CONTRACT,
    UPLOAD_MANAGER_ORDER_DOCUMENT,
    GET_MANAGER_DOC_DOWNLOAD,
    DELETE_MANAGER_DOC,
    GET_DOC_TEMPLATES,
    LIST_MANAGER_DOCUMENT_TEMPLATES,
    LIST_MANAGER_DOCUMENT_TEMPLATE_FILES,
    CREATE_MANAGER_DOCUMENT_TEMPLATE,
    PATCH_MANAGER_DOCUMENT_TEMPLATE,
    DELETE_MANAGER_DOCUMENT_TEMPLATE,
)
from schemas import (
    ManagerOrderDocumentListResponse,
    ManagerOrderDocumentItem,
    ManagerActionMessageResponse,
    DocumentTemplateListResponse,
    DocumentTemplateItem,
    DocumentTemplateFileItem,
    DocumentTemplateFileListResponse,
    DocumentTemplatePayload,
    DocumentTemplateUpdatePayload,
)
from services.document_service import (
    DocumentHasDependentsError,
    DocumentService,
    NativeManagedDocumentError,
    OrderDocumentsLockedError,
)
from services.document_template_service import DocumentTemplateService
from services.google_oauth_credentials import GoogleCredentialsError, GoogleDriveListError
from services.google_service import get_google_service
from services.tenant_entity_access_service import TenantEntityAccessService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/manager", tags=["manager-docs"])

DEFAULT_DOCUMENT_TEMPLATE_FOLDER_ID = "1SClclCJS2FUVtfF-vbVqN8zI77Sl_E9t"
DOCUMENT_TEMPLATE_FILES_UNAVAILABLE = "document_template_files_unavailable"
DOCUMENT_TEMPLATE_FILES_UNAVAILABLE_MESSAGE = (
    "Список файлов шаблонов временно недоступен"
)


def _document_template_files_google_error(
    exc: GoogleCredentialsError | GoogleDriveListError,
):
    logger.warning(
        "Document template files are unavailable error_type=%s",
        type(exc).__name__,
    )
    return manager_http_error(
        status_code=502,
        endpoint=LIST_MANAGER_DOCUMENT_TEMPLATE_FILES,
        error_code=DOCUMENT_TEMPLATE_FILES_UNAVAILABLE,
        message=DOCUMENT_TEMPLATE_FILES_UNAVAILABLE_MESSAGE,
    )


def _order_documents_locked_error(endpoint: str, exc: OrderDocumentsLockedError):
    return manager_http_error(
        status_code=409,
        endpoint=endpoint,
        error_code=ORDER_DOCUMENTS_LOCKED,
        message=str(exc),
    )


@router.get(
    "/orders/{order_id}/documents",
    response_model=ManagerOrderDocumentListResponse,
    operation_id=GET_MANAGER_ORDER_DOCUMENTS,
)
async def get_manager_order_documents(
    order_id: int,
    include_native: bool = Query(False),
    document_type: str | None = Query(None),
    site_id: int | None = Query(None, ge=1),
    equipment_id: int | None = Query(None, ge=1),
    limit: int | None = Query(None, ge=1, le=100),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    List legacy-compatible document metadata for an order in the current Manager
    tenant/storefront, including basis, scope snapshots and private external file history.
    Filter by semantic type, site or equipment and optionally include native documents.
    Missing order returns 404. Native artifacts/lifecycle use document-system endpoints.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    order_documents = await DocumentService.list_order_documents(
        session, order_id, tenant_scope=tenant_scope, include_native=True,
    )
    if order_documents is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_ORDER_DOCUMENTS,
            error_code=ORDER_NOT_FOUND,
        )
    docs = [d for d in order_documents if (
        (include_native or not DocumentService._is_native_managed_document(d))
        and (document_type is None or d.doc_type == document_type)
        and (site_id is None or site_id == (d.scope_meta or {}).get("site_id")
             or site_id in ((d.scope_meta or {}).get("site_ids") or []))
        and (equipment_id is None or equipment_id in ((d.scope_meta or {}).get("equipment_ids") or []))
    )][:limit]
    basis = await DocumentService.build_document_basis_lookup(session, order_documents)
    files = await ExternalOrderDocumentService.files_by_document(session, tenant_scope, docs)
    return {"items": [document_item(d, files.get(d.id, []), basis.get(d.id)) for d in docs]}


@router.post(
    "/orders/{order_id}/documents/upload",
    response_model=ManagerOrderDocumentItem,
    operation_id=UPLOAD_MANAGER_ORDER_DOCUMENT,
)
async def upload_manager_order_document(
    order_id: int,
    file: UploadFile = File(...),
    document_type: ExternalDocumentType | None = Form(None),
    number: str | None = Form(None),
    document_date: date | None = Form(None),
    external_status: ExternalDocumentStatus | None = Form(None),
    site_id: int | None = Form(None),
    equipment_ids: list[int] | None = Form(None),
    base_document_id: int | None = Form(None),
    proposal_id: int | None = Form(None),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Upload a DOC, DOCX or PDF to an accessible order in the current tenant/storefront.
    Provide document_type, number, document_date and Idempotency-Key for typed private
    evidence with immutable versions. An optional site/equipment must belong to the order.
    Typed and legacy uploads return 409 on closed orders. The existing file-only request
    retains legacy provider behavior and should be reconciled before retrying.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    if document_type is not None or idempotency_key is not None or any(value is not None for value in (
        number, document_date, external_status, site_id, equipment_ids, base_document_id, proposal_id,
    )):
        return await create_external_document(
            session, auth, UPLOAD_MANAGER_ORDER_DOCUMENT, order_id,
            {"document_type": document_type, "number": number, "document_date": document_date,
             "external_status": external_status or "received", "site_id": site_id,
             "equipment_ids": equipment_ids or [], "base_document_id": base_document_id,
             "proposal_id": proposal_id}, file, idempotency_key,
        )
    try:
        doc = await DocumentService.upload_document(
            session,
            order_id,
            file,
            tenant_scope=tenant_scope,
        )
    except OrderDocumentsLockedError as exc:
        raise _order_documents_locked_error(UPLOAD_MANAGER_ORDER_DOCUMENT, exc) from exc
    return document_item(doc)


@router.post(
    "/orders/{order_id}/documents/external-contract",
    response_model=ManagerOrderDocumentItem,
    operation_id=REGISTER_MANAGER_EXTERNAL_CONTRACT,
)
async def register_manager_external_contract(
    order_id: int,
    number: str = Form(...),
    contract_date: datetime = Form(...),
    external_url: str | None = Form(None),
    file: UploadFile | None = File(None),
    external_status: ExternalDocumentStatus | None = Form(None),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Register an external contract’s number/date and optional original for a scoped order.
    Supply Idempotency-Key and optionally external_status to record typed private evidence.
    Typed registration accepts DOC, DOCX and PDF and never fetches a URL or replaces the
    order’s selected framework agreement. Legacy optional reference URLs/files remain
    compatible. Closed orders return 409.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    if external_status is not None or idempotency_key is not None:
        if external_url:
            raise manager_http_error(
                status_code=400, endpoint=REGISTER_MANAGER_EXTERNAL_CONTRACT, error_code=BAD_REQUEST,
                message="Для внешнего договора загрузите исходный файл.",
            )
        return await create_external_document(
            session, auth, REGISTER_MANAGER_EXTERNAL_CONTRACT, order_id,
            {"document_type": "contract", "number": number, "document_date": contract_date.date(),
             "external_status": external_status or "received"}, file, idempotency_key,
        )
    try:
        doc = await DocumentService.register_external_contract(
            session,
            order_id=order_id,
            number=number,
            contract_date=contract_date,
            external_url=external_url,
            file=file,
            tenant_scope=tenant_scope,
        )
    except OrderDocumentsLockedError as exc:
        raise _order_documents_locked_error(REGISTER_MANAGER_EXTERNAL_CONTRACT, exc) from exc
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=REGISTER_MANAGER_EXTERNAL_CONTRACT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    return document_item(doc)


@router.post(
    "/docs/{doc_id}/file",
    response_model=ManagerOrderDocumentItem,
    operation_id=ATTACH_MANAGER_DOC_FILE,
)
async def attach_manager_doc_file(
    doc_id: int,
    file: UploadFile = File(...),
    file_role: ExternalDocumentFileRole | None = Form(None),
    expected_version: int | None = Form(None, ge=0),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    auth: AuthenticatedUser = Depends(require_manager_access),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Append a private file to an accessible document using file_role, expected_version and
    Idempotency-Key. Signed PDF copies may be attached to eligible closed/issued documents
    without changing the issued record. A stale version returns 409. A file-only request
    retains legacy provider behavior for mutable legacy documents.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    if file_role is not None or expected_version is not None or idempotency_key is not None:
        return await attach_external_document(
            session, auth, ATTACH_MANAGER_DOC_FILE, doc_id, file, file_role, expected_version, idempotency_key,
        )
    try:
        doc = await DocumentService.attach_file_to_document(
            session,
            doc_id,
            file,
            tenant_scope=tenant_scope,
        )
    except OrderDocumentsLockedError as exc:
        raise _order_documents_locked_error(ATTACH_MANAGER_DOC_FILE, exc) from exc
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=ATTACH_MANAGER_DOC_FILE,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not doc:
        raise manager_http_error(
            status_code=404,
            endpoint=ATTACH_MANAGER_DOC_FILE,
            error_code=DOCUMENT_NOT_FOUND,
        )
    return document_item(doc)


@router.get(
    "/docs/{doc_id}/download",
    operation_id=GET_MANAGER_DOC_DOWNLOAD,
)
async def get_manager_doc_download(
    doc_id: int,
    file_version: int | None = Query(None, ge=1),
    preview: bool = Query(False),
    preview_page: int = Query(1, ge=1, le=100),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Download a document’s stored original, explicitly selected private file_version, or
    legacy provider file under current tenant/storefront access. For a private PDF,
    preview=true returns the requested preview_page as a raster PNG without exposing
    the original PDF in an inline response. Missing document or file returns 404.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    external = await download_external_document(
        session, tenant_scope, GET_MANAGER_DOC_DOWNLOAD, doc_id, file_version, preview, preview_page,
    )
    if external is not None:
        return external
    try:
        pdf_content, filename_encoded = await DocumentService.get_download_stream(
            session,
            doc_id,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=GET_MANAGER_DOC_DOWNLOAD,
            error_code=BAD_REQUEST,
            message=str(exc),
        )

    if not pdf_content:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_DOC_DOWNLOAD,
            error_code=DOCUMENT_NOT_FOUND,
        )

    filename = unquote(filename_encoded)
    media_type = DocumentService.DEFAULT_UPLOAD_MIME_TYPES.get(
        PurePath(filename).suffix.lower(), "application/pdf"
    )
    return StreamingResponse(
        pdf_content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"
        },
    )


@router.delete(
    "/docs/{doc_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_DOC,
)
async def delete_manager_doc(
    doc_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Delete an accessible legacy document record and attempt provider file cleanup. Current
    tenant/storefront Manager access is required. Closed order, dependent documents or a
    native-managed lifecycle record returns 409; missing document returns 404. Provider
    cleanup failure does not imply the database record survived. A repeated delete is not
    receipt replay.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        order_id = await DocumentService.delete_document(
            session,
            doc_id,
            tenant_scope=tenant_scope,
        )
    except OrderDocumentsLockedError as exc:
        raise _order_documents_locked_error(DELETE_MANAGER_DOC, exc) from exc
    except DocumentHasDependentsError as exc:
        raise manager_http_error(
            status_code=409,
            endpoint=DELETE_MANAGER_DOC,
            error_code=DOCUMENT_HAS_DEPENDENTS,
            message=str(exc),
        ) from exc
    except NativeManagedDocumentError as exc:
        raise manager_http_error(
            status_code=409,
            endpoint=DELETE_MANAGER_DOC,
            error_code=DOCUMENT_MANAGED_BY_NATIVE,
            message=str(exc),
        ) from exc
    
    if not order_id:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_MANAGER_DOC,
            error_code=DOCUMENT_NOT_FOUND,
        )

    return {"message": "Document deleted"}


@router.get(
    "/docs/document-templates",
    response_model=DocumentTemplateListResponse,
    operation_id=LIST_MANAGER_DOCUMENT_TEMPLATES,
)
async def list_manager_document_templates(
    doc_type: str | None = Query(None),
    _: TenantScope = Depends(require_system_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    List the shared managed legacy Google template directory, excluding implicit legacy
    templates and optionally filtering by document type. Requires system-tenant Manager
    access; this is not the tenant-owned native template registry.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    items = await DocumentTemplateService.list_template_items(session, doc_type, include_legacy=False)
    return {"items": [DocumentTemplateItem(**item) for item in items]}


@router.get(
    "/docs/document-template-files",
    response_model=DocumentTemplateFileListResponse,
    operation_id=LIST_MANAGER_DOCUMENT_TEMPLATE_FILES,
)
async def list_manager_document_template_files(
    folder_id: str = Query(DEFAULT_DOCUMENT_TEMPLATE_FOLDER_ID),
    limit: int = Query(100, ge=1, le=200),
    _: TenantScope = Depends(require_system_manager_tenant_scope),
):
    """
    Read candidate files from the configured/shared Google Drive template folder. Requires
    system-tenant Manager access. This existing endpoint accepts limit 1–200, default 100;
    credentials/provider listing failure returns 502. Listing does not create a template
    definition or copy files.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        files = await run_in_threadpool(
            lambda: get_google_service().list_files(folder_id, limit=limit)
        )
    except (GoogleCredentialsError, GoogleDriveListError) as exc:
        raise _document_template_files_google_error(exc) from exc
    return {
        "items": [
            DocumentTemplateFileItem(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                mime_type=item.get("mimeType"),
                created_time=item.get("createdTime"),
            )
            for item in files
            if item.get("id") and item.get("name")
        ]
    }


@router.post(
    "/docs/document-templates",
    response_model=DocumentTemplateItem,
    operation_id=CREATE_MANAGER_DOCUMENT_TEMPLATE,
)
async def create_manager_document_template(
    payload: DocumentTemplatePayload,
    _: TenantScope = Depends(require_system_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a shared legacy Google template definition from a Drive file reference and
    supplied restrictions/basis links. Requires system-tenant Manager access. Invalid
    configuration returns 400; this does not upload a native DOCX version. No caller
    idempotency receipt is provided.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        item = await DocumentTemplateService.create_template(session, payload)
        return DocumentTemplateItem(**item)
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=CREATE_MANAGER_DOCUMENT_TEMPLATE, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.patch(
    "/docs/document-templates/{template_id}",
    response_model=DocumentTemplateItem,
    operation_id=PATCH_MANAGER_DOCUMENT_TEMPLATE,
)
async def patch_manager_document_template(
    template_id: int,
    payload: DocumentTemplateUpdatePayload,
    _: TenantScope = Depends(require_system_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    Patch supplied fields of a shared legacy Google template definition. Requires
    system-tenant Manager access. Invalid or missing template configuration returns 400;
    existing generated document files are not regenerated by this metadata update.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        item = await DocumentTemplateService.update_template(session, template_id, payload)
        return DocumentTemplateItem(**item)
    except ValueError as exc:
        raise manager_http_error(status_code=400, endpoint=PATCH_MANAGER_DOCUMENT_TEMPLATE, error_code=BAD_REQUEST, message=str(exc)) from exc


@router.delete(
    "/docs/document-templates/{template_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_DOCUMENT_TEMPLATE,
)
async def delete_manager_document_template(
    template_id: int,
    _: TenantScope = Depends(require_system_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete a shared legacy template definition after service dependency validation. Requires
    system-tenant Manager access. A missing definition or service refusal is returned as
    404; repeating deletion is not an idempotent receipt.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        await DocumentTemplateService.delete_template(session, template_id)
        return {"message": "Document template deleted"}
    except ValueError as exc:
        raise manager_http_error(status_code=404, endpoint=DELETE_MANAGER_DOCUMENT_TEMPLATE, error_code=DOCUMENT_NOT_FOUND, message=str(exc)) from exc


@router.get(
    "/docs/templates/{doc_type}",
    response_model=DocumentTemplateListResponse,
    operation_id=GET_DOC_TEMPLATES,
)
async def get_doc_templates(
    doc_type: str,
    order_id: int | None = Query(None),
    customer_id: int | None = Query(None),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Resolve available legacy templates for a document kind and optional order/customer
    context. Manager access and scoped entity checks are required; partner tenants must
    supply order or customer context (403 otherwise). Missing/inaccessible context returns
    404. Partner responses restrict exposed customer IDs to the selected customer; this does
    not grant access to shared template administration.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    selected_customer_id = customer_id
    if not tenant_scope.is_system and order_id is None and customer_id is None:
        raise HTTPException(
            status_code=403,
            detail="Order or customer context required",
        )
    if order_id is not None:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if order is None:
            raise manager_http_error(
                status_code=404,
                endpoint=GET_DOC_TEMPLATES,
                error_code=ORDER_NOT_FOUND,
            )
        selected_customer_id = order.customer_id
    if customer_id is not None:
        customer = await TenantEntityAccessService.get_customer(
            session,
            customer_id,
            tenant_scope=tenant_scope,
        )
        if customer is None:
            raise manager_http_error(
                status_code=404,
                endpoint=GET_DOC_TEMPLATES,
                error_code=CUSTOMER_NOT_FOUND,
            )
    items = await DocumentService.get_available_templates(session, doc_type, order_id=order_id, customer_id=customer_id)
    if not tenant_scope.is_system:
        items = [
            {
                **item,
                "customer_ids": [
                    value
                    for value in item.get("customer_ids") or []
                    if selected_customer_id is not None
                    and int(value) == int(selected_customer_id)
                ],
            }
            for item in items
        ]
    return {
        "items": [
            DocumentTemplateItem(
                id=t["id"],
                document_template_id=t.get("document_template_id"),
                name=t["name"],
                document_role_type=t.get("document_role_type"),
                is_open_contract=bool(t.get("is_open_contract")),
                doc_type=t.get("doc_type", doc_type),
                description=t.get("description"),
                base_document_type_label=t.get("base_document_type_label"),
                is_default=bool(t.get("is_default")),
                is_active=bool(t.get("is_active", True)),
                client_restricted=bool(t.get("client_restricted")),
                sort_order=int(t.get("sort_order") or 0),
                customer_ids=t.get("customer_ids") or [],
                linked_contract_template_ids=t.get("linked_contract_template_ids") or [],
                linked_act_template_ids=t.get("linked_act_template_ids") or [],
            )
            for t in items
        ]
    }
