from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import DOCUMENT_NOT_FOUND, BAD_REQUEST
from core.security import get_current_username
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
from services.document_service import DocumentService
from services.document_template_service import DocumentTemplateService
from services.google_service import get_google_service


router = APIRouter(prefix="/api/manager", tags=["manager-docs"])

DEFAULT_DOCUMENT_TEMPLATE_FOLDER_ID = "1SClclCJS2FUVtfF-vbVqN8zI77Sl_E9t"


@router.get(
    "/orders/{order_id}/documents",
    response_model=ManagerOrderDocumentListResponse,
    operation_id=GET_MANAGER_ORDER_DOCUMENTS,
)
async def get_manager_order_documents(
    order_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    docs = await DocumentService.list_order_documents(session, order_id)
    basis_lookup = await DocumentService.build_document_basis_lookup(session, list(docs))
    return {
        "items": [
            ManagerOrderDocumentItem(
                id=d.id,
                proposal_id=d.proposal_id,
                **basis_lookup.get(d.id, {}),
                scope_customer_branch_id=d.scope_customer_branch_id,
                scope_title=d.scope_title,
                scope_address=d.scope_address,
                scope_meta=d.scope_meta or {},
                doc_type=d.doc_type,
                number=d.number,
                date=d.date,
                edit_url=d.google_edit_url,
                is_downloadable=bool(d.google_file_id),
            )
            for d in docs
        ]
    }


@router.post(
    "/orders/{order_id}/documents/upload",
    response_model=ManagerOrderDocumentItem,
    operation_id=UPLOAD_MANAGER_ORDER_DOCUMENT,
)
async def upload_manager_order_document(
    order_id: int,
    file: UploadFile = File(...),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    doc = await DocumentService.upload_document(session, order_id, file)
    return ManagerOrderDocumentItem(
        id=doc.id,
        proposal_id=doc.proposal_id,
        base_document_id=doc.base_document_id,
        base_customer_contract_id=doc.base_customer_contract_id,
        scope_customer_branch_id=doc.scope_customer_branch_id,
        scope_title=doc.scope_title,
        scope_address=doc.scope_address,
        scope_meta=doc.scope_meta or {},
        doc_type=doc.doc_type,
        number=doc.number,
        date=doc.date,
        edit_url=doc.google_edit_url,
        is_downloadable=bool(doc.google_file_id),
    )


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
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        doc = await DocumentService.register_external_contract(
            session,
            order_id=order_id,
            number=number,
            contract_date=contract_date,
            external_url=external_url,
            file=file,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=REGISTER_MANAGER_EXTERNAL_CONTRACT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    return ManagerOrderDocumentItem(
        id=doc.id,
        proposal_id=doc.proposal_id,
        base_document_id=doc.base_document_id,
        base_customer_contract_id=doc.base_customer_contract_id,
        scope_customer_branch_id=doc.scope_customer_branch_id,
        scope_title=doc.scope_title,
        scope_address=doc.scope_address,
        scope_meta=doc.scope_meta or {},
        doc_type=doc.doc_type,
        number=doc.number,
        date=doc.date,
        edit_url=doc.google_edit_url,
        is_downloadable=bool(doc.google_file_id),
    )


@router.post(
    "/docs/{doc_id}/file",
    response_model=ManagerOrderDocumentItem,
    operation_id=ATTACH_MANAGER_DOC_FILE,
)
async def attach_manager_doc_file(
    doc_id: int,
    file: UploadFile = File(...),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        doc = await DocumentService.attach_file_to_document(session, doc_id, file)
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
    return ManagerOrderDocumentItem(
        id=doc.id,
        proposal_id=doc.proposal_id,
        base_document_id=doc.base_document_id,
        base_customer_contract_id=doc.base_customer_contract_id,
        scope_customer_branch_id=doc.scope_customer_branch_id,
        scope_title=doc.scope_title,
        scope_address=doc.scope_address,
        scope_meta=doc.scope_meta or {},
        doc_type=doc.doc_type,
        number=doc.number,
        date=doc.date,
        edit_url=doc.google_edit_url,
        is_downloadable=bool(doc.google_file_id),
    )


@router.get(
    "/docs/{doc_id}/download",
    operation_id=GET_MANAGER_DOC_DOWNLOAD,
)
async def get_manager_doc_download(
    doc_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        pdf_content, filename_encoded = await DocumentService.get_download_stream(session, doc_id)
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

    return StreamingResponse(
        pdf_content,
        media_type="application/pdf",
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
):
    order_id = await DocumentService.delete_document(session, doc_id)
    
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
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
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
    _: str = Depends(get_current_username),
):
    files = await run_in_threadpool(lambda: get_google_service().list_files(folder_id, limit=limit))
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
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
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
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
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
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
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
):
    items = await DocumentService.get_available_templates(session, doc_type, order_id=order_id, customer_id=customer_id)
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
