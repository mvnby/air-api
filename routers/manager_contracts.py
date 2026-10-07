from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, CUSTOMER_NOT_FOUND
from core.security import get_current_manager_tenant_scope
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    ARCHIVE_MANAGER_CUSTOMER_CONTRACT,
    CREATE_MANAGER_CUSTOMER_CONTRACT,
    DELETE_MANAGER_CUSTOMER_CONTRACT,
    GET_MANAGER_CUSTOMER_CONTRACTS,
    PATCH_MANAGER_CUSTOMER_CONTRACT,
    UPLOAD_MANAGER_CUSTOMER_CONTRACT,
)
from schemas import (
    ManagerActionMessageResponse,
    ManagerCustomerContractCreatePayload,
    ManagerCustomerContractItemResponse,
    ManagerCustomerContractListResponse,
    ManagerCustomerContractUpdatePayload,
)
from services.customer_contract_service import CustomerContractService


router = APIRouter(prefix="/api/manager/customers", tags=["manager-contracts"])


@router.get(
    "/{customer_id}/contracts",
    response_model=ManagerCustomerContractListResponse,
    operation_id=GET_MANAGER_CUSTOMER_CONTRACTS,
)
async def get_manager_customer_contracts(
    customer_id: int,
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    List active and archived open contracts for a customer owned by the current tenant, with
    provider edit links. Missing or inaccessible customer returns 404. Reading does not
    generate a contract.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    data = await CustomerContractService.list_for_customer(
        session,
        customer_id,
        tenant_scope=tenant_scope,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_CUSTOMER_CONTRACTS,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "/{customer_id}/contracts",
    response_model=ManagerCustomerContractItemResponse,
    operation_id=CREATE_MANAGER_CUSTOMER_CONTRACT,
)
async def create_manager_customer_contract(
    customer_id: int,
    payload: ManagerCustomerContractCreatePayload,
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    Generate a new open contract from the configured shared Google template for a
    current-tenant company or individual entrepreneur. Copies the provider file and
    substitutes current customer requisites; omitted number is allocated by the contract
    service and omitted expiry defaults to one year. Missing customer returns 404;
    unsupported party type or unavailable open-contract template returns 400. Repeating POST
    creates another contract/file; no caller replay receipt is supplied.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        data = await CustomerContractService.create_for_customer(
            session,
            customer_id=customer_id,
            payload=payload.model_dump(exclude_unset=True),
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_CUSTOMER_CONTRACT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_CUSTOMER_CONTRACT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "/{customer_id}/contracts/upload",
    response_model=ManagerCustomerContractItemResponse,
    operation_id=UPLOAD_MANAGER_CUSTOMER_CONTRACT,
)
async def upload_manager_customer_contract(
    customer_id: int,
    number: str = Form(...),
    contract_date: datetime = Form(...),
    valid_until: datetime = Form(...),
    template_id: str | None = Form(None),
    document_role_type: str | None = Form(None),
    file: UploadFile = File(...),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    Upload an existing open-contract file to the configured Google provider and register it
    for a current-tenant company or individual entrepreneur. Requires number, contract date,
    expiry and a configured template marked as open contract. Missing customer returns 404;
    unsupported party/template or invalid metadata returns 400. No caller replay receipt or
    route-specific file-size limit is supplied; repeating POST can create another
    file/record.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        data = await CustomerContractService.upload_for_customer(
            session,
            customer_id=customer_id,
            number=number,
            contract_date=contract_date,
            valid_until=valid_until,
            template_id=template_id,
            document_role_type=document_role_type,
            file=file,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=UPLOAD_MANAGER_CUSTOMER_CONTRACT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=UPLOAD_MANAGER_CUSTOMER_CONTRACT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.patch(
    "/{customer_id}/contracts/{contract_id}",
    response_model=ManagerCustomerContractItemResponse,
    operation_id=PATCH_MANAGER_CUSTOMER_CONTRACT,
)
async def patch_manager_customer_contract(
    customer_id: int,
    contract_id: int,
    payload: ManagerCustomerContractUpdatePayload,
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    Patch supplied metadata of an open contract belonging to the current-tenant customer.
    Number/date/expiry/document-role changes also attempt placeholder replacement in its
    Google file; this is not immutable native document versioning. Missing customer/contract
    returns 404; empty number or unsupported status returns 400. No expected_version
    precondition is provided.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        data = await CustomerContractService.update_for_customer(
            session,
            customer_id=customer_id,
            contract_id=contract_id,
            payload=payload.model_dump(exclude_unset=True),
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_CUSTOMER_CONTRACT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_CUSTOMER_CONTRACT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "/{customer_id}/contracts/{contract_id}/archive",
    response_model=ManagerActionMessageResponse,
    operation_id=ARCHIVE_MANAGER_CUSTOMER_CONTRACT,
)
async def archive_manager_customer_contract(
    customer_id: int,
    contract_id: int,
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    Mark an open contract of the current-tenant customer archived, retaining its file and
    existing order references. Repeating archive sets the same state; no separate replay
    receipt is supplied. Missing customer/contract returns 404. This does not delete or
    regenerate the contract.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    ok = await CustomerContractService.archive_for_customer(
        session,
        customer_id=customer_id,
        contract_id=contract_id,
        tenant_scope=tenant_scope,
    )
    if ok is None:
        raise manager_http_error(
            status_code=404,
            endpoint=ARCHIVE_MANAGER_CUSTOMER_CONTRACT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return {"message": "Contract archived"}


@router.delete(
    "/{customer_id}/contracts/{contract_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_CUSTOMER_CONTRACT,
)
async def delete_manager_customer_contract(
    customer_id: int,
    contract_id: int,
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    session: AsyncSession = Depends(get_session),
):
    """
    Delete an open-contract record of the current-tenant customer, clear orders’ references
    to it and attempt Google file deletion. Provider cleanup is best effort, so success does
    not prove the remote file was removed. Missing customer/contract returns 404, including
    a repeat after deletion. Archiving is the alternative when the record should remain.

    Access requires an authenticated Manager session/JWT and live membership; see [Manager
    access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    ok = await CustomerContractService.delete_for_customer(
        session,
        customer_id=customer_id,
        contract_id=contract_id,
        tenant_scope=tenant_scope,
    )
    if ok is None:
        raise manager_http_error(
            status_code=404,
            endpoint=DELETE_MANAGER_CUSTOMER_CONTRACT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return {"message": "Contract deleted"}
