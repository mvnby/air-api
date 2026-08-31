from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import (
    BAD_REQUEST,
    CUSTOMER_ALREADY_EXISTS,
    CUSTOMER_NOT_FOUND,
)
from core.security import get_current_manager_tenant_scope
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    CONFIRM_MANAGER_CUSTOMER_REQUISITES,
    CREATE_MANAGER_CUSTOMER,
    CREATE_MANAGER_CUSTOMER_BRANCH,
    CREATE_MANAGER_CUSTOMER_RECONCILIATION_DOCUMENT,
    DELETE_MANAGER_CUSTOMER,
    DELETE_MANAGER_CUSTOMER_BRANCH,
    GET_MANAGER_CUSTOMER_BRANCHES,
    GET_MANAGER_CUSTOMER_DETAIL,
    GET_MANAGER_CUSTOMER_DOCS,
    GET_MANAGER_CUSTOMER_RECONCILIATION,
    GET_MANAGER_CUSTOMERS,
    PATCH_MANAGER_CUSTOMER,
    PATCH_MANAGER_CUSTOMER_BRANCH,
    RECOGNIZE_MANAGER_CUSTOMER_REQUISITES,
)
from schemas import (
    CustomerRequisitesConfirmPayload,
    CustomerRequisitesConfirmResponse,
    CustomerRequisitesRecognitionResponse,
    ManagerActionMessageResponse,
    ManagerCatalogCustomerItemResponse,
    ManagerCatalogCustomerListResponse,
    ManagerCustomerBranchCreatePayload,
    ManagerCustomerBranchItemResponse,
    ManagerCustomerBranchListResponse,
    ManagerCustomerBranchUpdatePayload,
    ManagerCustomerCreatePayload,
    ManagerCustomerDocumentListResponse,
    ManagerCustomerReconciliationDocumentResponse,
    ManagerCustomerReconciliationResponse,
    ManagerCustomerUpdatePayload,
)
from services.customer_reconciliation_service import CustomerReconciliationService
from services.customer_requisites_recognition_service import CustomerRequisitesRecognitionService
from services.customer_creation_service import CustomerAlreadyExistsError
from services.customer_service import CustomerService
from services.document_service import DocumentService
from services.manager_catalog_service import ManagerCatalogService


router = APIRouter()


@router.get(
    "/customers",
    response_model=ManagerCatalogCustomerListResponse,
    operation_id=GET_MANAGER_CUSTOMERS,
)
async def list_customers_for_manager(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    customer_type: Optional[str] = Query(None, alias="type"),
    only_with_orders: bool = Query(True),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Paginated customer list for manager UI.
    Includes order count per customer.
    """
    return await ManagerCatalogService.list_customers(
        session=session,
        page=page,
        limit=limit,
        search=search,
        customer_type=customer_type,
        only_with_orders=only_with_orders,
        tenant_scope=tenant_scope,
    )


@router.post(
    "/customers",
    response_model=ManagerCatalogCustomerItemResponse,
    status_code=201,
    operation_id=CREATE_MANAGER_CUSTOMER,
)
async def create_customer_for_manager(
    payload: ManagerCustomerCreatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await ManagerCatalogService.create_customer(
            session=session,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except CustomerAlreadyExistsError as exc:
        raise manager_http_error(
            status_code=409,
            endpoint=CREATE_MANAGER_CUSTOMER,
            error_code=CUSTOMER_ALREADY_EXISTS,
            message=str(exc),
            field_errors={
                "duplicate_customer_id": str(exc.customer_id),
                "duplicate_fields": ",".join(exc.matched_fields),
            },
        ) from exc
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_CUSTOMER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/customers/requisites/recognize",
    response_model=CustomerRequisitesRecognitionResponse,
    operation_id=RECOGNIZE_MANAGER_CUSTOMER_REQUISITES,
)
async def recognize_customer_requisites_for_manager(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        content = await file.read()
        return await CustomerRequisitesRecognitionService.recognize_bytes(
            session,
            content=content,
            filename=file.filename,
            mime_type=file.content_type,
            source="manager",
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=RECOGNIZE_MANAGER_CUSTOMER_REQUISITES,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/customers/requisites/{recognition_id}/confirm",
    response_model=CustomerRequisitesConfirmResponse,
    operation_id=CONFIRM_MANAGER_CUSTOMER_REQUISITES,
)
async def confirm_customer_requisites_for_manager(
    recognition_id: int,
    payload: CustomerRequisitesConfirmPayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        return await CustomerRequisitesRecognitionService.confirm(
            session,
            recognition_id=recognition_id,
            action=payload.action,
            customer_id=payload.customer_id,
            tenant_scope=tenant_scope,
        )
    except LookupError as exc:
        raise manager_http_error(
            status_code=404,
            endpoint=CONFIRM_MANAGER_CUSTOMER_REQUISITES,
            error_code=CUSTOMER_NOT_FOUND,
            message=str(exc),
        ) from exc
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CONFIRM_MANAGER_CUSTOMER_REQUISITES,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.get(
    "/customers/{customer_id}",
    response_model=ManagerCatalogCustomerItemResponse,
    operation_id=GET_MANAGER_CUSTOMER_DETAIL,
)
async def get_customer_for_manager(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    customer = await ManagerCatalogService.get_customer(
        session=session,
        customer_id=customer_id,
        tenant_scope=tenant_scope,
    )
    if not customer:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_CUSTOMER_DETAIL,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return customer


@router.get(
    "/customers/{customer_id}/docs",
    response_model=ManagerCustomerDocumentListResponse,
    operation_id=GET_MANAGER_CUSTOMER_DOCS,
)
async def get_customer_docs_for_manager(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    docs = await DocumentService.get_customer_documents(
        session,
        customer_id,
        tenant_scope=tenant_scope,
    )
    if docs is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_CUSTOMER_DOCS,
            error_code=CUSTOMER_NOT_FOUND,
        )
    basis_lookup = await DocumentService.build_document_basis_lookup(session, list(docs))
    return {
        "items": [
            {
                "id": doc.id,
                "order_id": doc.order_id,
                "proposal_id": doc.proposal_id,
                **basis_lookup.get(doc.id, {}),
                "scope_customer_branch_id": doc.scope_customer_branch_id,
                "scope_title": doc.scope_title,
                "scope_address": doc.scope_address,
                "scope_meta": doc.scope_meta or {},
                "doc_type": doc.doc_type,
                "number": doc.number,
                "date": doc.date,
                "edit_url": doc.google_edit_url,
                "is_downloadable": bool(doc.google_file_id),
            }
            for doc in docs
        ]
    }


@router.get(
    "/customers/{customer_id}/reconciliation",
    response_model=ManagerCustomerReconciliationResponse,
    operation_id=GET_MANAGER_CUSTOMER_RECONCILIATION,
)
async def get_customer_reconciliation_for_manager(
    customer_id: int,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    data = await CustomerReconciliationService.build(
        session=session,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        tenant_scope=tenant_scope,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_CUSTOMER_RECONCILIATION,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "/customers/{customer_id}/reconciliation/document",
    response_model=ManagerCustomerReconciliationDocumentResponse,
    operation_id=CREATE_MANAGER_CUSTOMER_RECONCILIATION_DOCUMENT,
)
async def create_customer_reconciliation_document_for_manager(
    customer_id: int,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    data = await CustomerReconciliationService.generate_google_doc(
        session=session,
        customer_id=customer_id,
        date_from=date_from,
        date_to=date_to,
        tenant_scope=tenant_scope,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_CUSTOMER_RECONCILIATION_DOCUMENT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.get(
    "/customers/{customer_id}/branches",
    response_model=ManagerCustomerBranchListResponse,
    operation_id=GET_MANAGER_CUSTOMER_BRANCHES,
)
async def list_customer_branches_for_manager(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    data = await ManagerCatalogService.list_customer_branches(
        session=session,
        customer_id=customer_id,
        tenant_scope=tenant_scope,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_CUSTOMER_BRANCHES,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "/customers/{customer_id}/branches",
    response_model=ManagerCustomerBranchItemResponse,
    operation_id=CREATE_MANAGER_CUSTOMER_BRANCH,
)
async def create_customer_branch_for_manager(
    customer_id: int,
    payload: ManagerCustomerBranchCreatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        data = await ManagerCatalogService.create_customer_branch(
            session=session,
            customer_id=customer_id,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_CUSTOMER_BRANCH,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_CUSTOMER_BRANCH,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.patch(
    "/customers/{customer_id}/branches/{branch_id}",
    response_model=ManagerCustomerBranchItemResponse,
    operation_id=PATCH_MANAGER_CUSTOMER_BRANCH,
)
async def patch_customer_branch_for_manager(
    customer_id: int,
    branch_id: int,
    payload: ManagerCustomerBranchUpdatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        data = await ManagerCatalogService.update_customer_branch(
            session=session,
            customer_id=customer_id,
            branch_id=branch_id,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_CUSTOMER_BRANCH,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_CUSTOMER_BRANCH,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.delete(
    "/customers/{customer_id}/branches/{branch_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_CUSTOMER_BRANCH,
)
async def delete_customer_branch_for_manager(
    customer_id: int,
    branch_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    data = await ManagerCatalogService.delete_customer_branch(
        session=session,
        customer_id=customer_id,
        branch_id=branch_id,
        tenant_scope=tenant_scope,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_MANAGER_CUSTOMER_BRANCH,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return {"message": "Branch deleted"}


@router.patch(
    "/customers/{customer_id}",
    response_model=ManagerCatalogCustomerItemResponse,
    operation_id=PATCH_MANAGER_CUSTOMER,
)
async def patch_customer_for_manager(
    customer_id: int,
    payload: ManagerCustomerUpdatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        customer = await ManagerCatalogService.update_customer(
            session=session,
            customer_id=customer_id,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_CUSTOMER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if not customer:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_CUSTOMER,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return customer


@router.delete(
    "/customers/{customer_id}",
    operation_id=DELETE_MANAGER_CUSTOMER,
)
async def delete_customer_for_manager(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    try:
        success = await CustomerService.delete_for_manager(
            session,
            customer_id,
            tenant_scope=tenant_scope,
        )
        if not success:
            raise manager_http_error(
                status_code=404,
                endpoint=DELETE_MANAGER_CUSTOMER,
                error_code=CUSTOMER_NOT_FOUND,
            )
        return {"ok": True}
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=DELETE_MANAGER_CUSTOMER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
