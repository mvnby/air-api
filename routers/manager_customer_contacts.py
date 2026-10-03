from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, CUSTOMER_NOT_FOUND
from core.security import AuthenticatedUser, get_current_manager_tenant_scope, require_manager_access
from models.tenancy import TenantScope
from schemas import (
    ManagerCustomerContactCreatePayload,
    ManagerCustomerContactHistoryResponse,
    ManagerCustomerContactItemResponse,
    ManagerCustomerContactListResponse,
    ManagerCustomerContactUpdatePayload,
)
from services.customer_contact_service import CustomerContactService
from routers.manager_operation_ids import (
    GET_MANAGER_CUSTOMER_CONTACTS,
    CREATE_MANAGER_CUSTOMER_CONTACT,
    PATCH_MANAGER_CUSTOMER_CONTACT,
    GET_MANAGER_CUSTOMER_CONTACT_HISTORY,
)


router = APIRouter()


@router.get(
    "/customers/{customer_id}/contacts",
    response_model=ManagerCustomerContactListResponse,
    operation_id=GET_MANAGER_CUSTOMER_CONTACTS,
)
async def get_manager_customer_contacts(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    result = await CustomerContactService.list_contacts(
        session, customer_id, tenant_scope=tenant_scope
    )
    if result is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_CUSTOMER_CONTACTS,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return result


@router.post(
    "/customers/{customer_id}/contacts",
    response_model=ManagerCustomerContactItemResponse,
    status_code=201,
    operation_id=CREATE_MANAGER_CUSTOMER_CONTACT,
)
async def create_manager_customer_contact(
    customer_id: int,
    payload: ManagerCustomerContactCreatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    try:
        result = await CustomerContactService.create_contact(
            session,
            customer_id,
            payload.model_dump(exclude_unset=True),
            tenant_scope=tenant_scope,
            author_id=auth.staff_user_id,
            author_name=auth.display_name or auth.username,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_CUSTOMER_CONTACT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if result is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_CUSTOMER_CONTACT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return result


@router.patch(
    "/customers/{customer_id}/contacts/{contact_id}",
    response_model=ManagerCustomerContactItemResponse,
    operation_id=PATCH_MANAGER_CUSTOMER_CONTACT,
)
async def patch_manager_customer_contact(
    customer_id: int,
    contact_id: int,
    payload: ManagerCustomerContactUpdatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    try:
        result = await CustomerContactService.patch_contact(
            session,
            customer_id,
            contact_id,
            payload.model_dump(exclude_unset=True),
            tenant_scope=tenant_scope,
            author_id=auth.staff_user_id,
            author_name=auth.display_name or auth.username,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_CUSTOMER_CONTACT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if result is None:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_CUSTOMER_CONTACT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return result


@router.get(
    "/customers/{customer_id}/contact-history",
    response_model=ManagerCustomerContactHistoryResponse,
    operation_id=GET_MANAGER_CUSTOMER_CONTACT_HISTORY,
)
async def get_manager_customer_contact_history(
    customer_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    result = await CustomerContactService.history(
        session, customer_id, tenant_scope=tenant_scope, page=page, limit=limit
    )
    if result is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_CUSTOMER_CONTACT_HISTORY,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return result
