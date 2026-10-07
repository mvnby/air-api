from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, CUSTOMER_NOT_FOUND, EQUIPMENT_NOT_FOUND, FORBIDDEN
from core.security import get_current_manager_tenant_scope, get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_EQUIPMENT_COMPONENT,
    CREATE_MANAGER_EQUIPMENT,
    CREATE_MANAGER_EQUIPMENT_FROM_ORDER,
    CREATE_MANAGER_MAINTENANCE_ORDER,
    CREATE_MANAGER_EQUIPMENT_HISTORY,
    CREATE_MANAGER_EQUIPMENT_HISTORY_FROM_REPAIR_ORDER,
    GET_MANAGER_EQUIPMENT,
    LIST_MANAGER_EQUIPMENT,
    LIST_MANAGER_EQUIPMENT_HISTORY,
    PATCH_MANAGER_EQUIPMENT_COMPONENT,
    PATCH_MANAGER_EQUIPMENT,
)
from schemas import (
    ManagerEquipmentComponentCreatePayload,
    ManagerEquipmentComponentItemResponse,
    ManagerEquipmentComponentUpdatePayload,
    ManagerEquipmentCreatePayload,
    ManagerEquipmentDetailResponse,
    ManagerEquipmentFromOrderPayload,
    ManagerEquipmentFromOrderResponse,
    ManagerEquipmentHistoryFromRepairOrderPayload,
    ManagerEquipmentItemResponse,
    ManagerEquipmentListResponse,
    ManagerOrderDetailResponse,
    ManagerEquipmentServiceHistoryCreatePayload,
    ManagerEquipmentServiceHistoryItemResponse,
    ManagerEquipmentServiceHistoryListResponse,
    ManagerEquipmentUpdatePayload,
)
from services.equipment_service import EquipmentService
from services.manager_equipment_permission_service import (
    ManagerEquipmentPermissionService,
    TenantEquipmentCommercialFieldsDeniedError,
)
from services.tenant_scope_service import TenantScope


router = APIRouter(prefix="/api/manager/equipment", tags=["manager-equipment"])


@router.get("", response_model=ManagerEquipmentListResponse, operation_id=LIST_MANAGER_EQUIPMENT)
async def list_manager_equipment(
    customer_id: Optional[int] = Query(None),
    customer_branch_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    include_archived: bool = Query(False),
    q: Optional[str] = Query(None, max_length=200),
    attention: Optional[str] = Query(None),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read the customer equipment register with customer/branch, text and attention filters;
    archived records are excluded by default. page starts at 1 and limit is 1–100. Invalid
    filter combinations return 400 and an inaccessible requested customer returns 404.
    Warranty and maintenance attention are projections, not automatic service orders.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [equipment and
    maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    try:
        data = await EquipmentService.list_equipment(
            session=session,
            customer_id=customer_id,
            customer_branch_id=customer_branch_id,
            page=page,
            limit=limit,
            include_archived=include_archived,
            q=q,
            attention=attention,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=LIST_MANAGER_EQUIPMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=LIST_MANAGER_EQUIPMENT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "",
    response_model=ManagerEquipmentItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT,
)
async def create_manager_equipment(
    payload: ManagerEquipmentCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create a customer equipment record, optional source-order association and applicable
    warranty snapshots. Invalid customer/branch/order/product relationships or dates return
    400; inaccessible customer returns 404. Supplier/invoice fields are writable only by the
    system tenant, even when explicitly submitted as null; partners receive 403. This POST
    has no idempotency receipt and repeated calls create additional equipment.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [equipment and
    maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    equipment_payload = payload.model_dump(exclude_unset=True)
    try:
        ManagerEquipmentPermissionService.assert_supplier_fields_allowed(
            payload=equipment_payload,
            tenant_scope=tenant_scope,
        )
        data = await EquipmentService.create_equipment(
            session=session,
            payload=equipment_payload,
            tenant_scope=tenant_scope,
        )
    except TenantEquipmentCommercialFieldsDeniedError as exc:
        raise manager_http_error(
            status_code=403,
            endpoint=CREATE_MANAGER_EQUIPMENT,
            error_code=FORBIDDEN,
            message=str(exc),
        ) from exc
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_EQUIPMENT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "/from-order/{order_id}",
    response_model=ManagerEquipmentFromOrderResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT_FROM_ORDER,
)
async def create_manager_equipment_from_order(
    order_id: int,
    payload: ManagerEquipmentFromOrderPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create missing equipment units from catalog products in the scoped order’s selected
    proposal, optionally adding component placeholders. Existing unarchived units with the
    same source order/product count toward the requested quantity, so ordinary repeats
    create only missing units; archived units do not count. Missing/ineligible order or
    incompatible input returns 400. Supplier/invoice fields are system-only (403 for partner
    submissions). This count-based workflow has no idempotency receipt.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [equipment and
    maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    equipment_payload = payload.model_dump(exclude_unset=True)
    try:
        ManagerEquipmentPermissionService.assert_supplier_fields_allowed(
            payload=equipment_payload,
            tenant_scope=tenant_scope,
        )
        return await EquipmentService.create_equipment_from_order(
            session=session,
            order_id=order_id,
            payload=equipment_payload,
            tenant_scope=tenant_scope,
        )
    except TenantEquipmentCommercialFieldsDeniedError as exc:
        raise manager_http_error(
            status_code=403,
            endpoint=CREATE_MANAGER_EQUIPMENT_FROM_ORDER,
            error_code=FORBIDDEN,
            message=str(exc),
        ) from exc
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT_FROM_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.post(
    "/{equipment_id}/maintenance-order",
    response_model=ManagerOrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_MAINTENANCE_ORDER,
)
async def create_manager_maintenance_order(
    equipment_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create a new maintenance order for equipment, copying customer/branch contact and
    address context and linking the equipment to the order. Missing/inaccessible or archived
    equipment returns 404; invalid creation data returns 400. This does not record completed
    maintenance or advance its due date. There is no reuse/idempotency receipt: each
    successful call creates another order. Order creation and subsequent equipment linking
    use separate commits.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [equipment and
    maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    try:
        data = await EquipmentService.create_maintenance_order(
            session=session,
            equipment_id=equipment_id,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_MAINTENANCE_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_MAINTENANCE_ORDER,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.get("/{equipment_id}", response_model=ManagerEquipmentDetailResponse, operation_id=GET_MANAGER_EQUIPMENT)
async def get_manager_equipment(
    equipment_id: int,
    history_limit: int = Query(10, ge=0, le=100),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read one customer equipment card with components, warranty coverages, maintenance
    projection, linked orders and recent service history. history_limit is 0–100; component
    supplier/invoice fields are redacted for partners. Missing or inaccessible equipment
    returns 404; reading does not refresh stored warranty definitions or create a
    maintenance event.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [equipment and
    maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    data = await EquipmentService.get_equipment_detail(
        session=session,
        equipment_id=equipment_id,
        history_limit=history_limit,
        tenant_scope=tenant_scope,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_EQUIPMENT,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.patch("/{equipment_id}", response_model=ManagerEquipmentItemResponse, operation_id=PATCH_MANAGER_EQUIPMENT)
async def patch_manager_equipment(
    equipment_id: int,
    payload: ManagerEquipmentUpdatePayload,
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Update submitted equipment metadata, location, dates, warranty mode and independent
    maintenance plan. Invalid references or an enabled maintenance plan without a usable
    anchor date return 400; missing equipment returns 404. Manual warranty changes preserve
    original coverage snapshots, and returning to auto restores those snapshots rather than
    selecting current policy definitions. No expected-version or idempotency receipt is
    required.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [equipment and
    maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    try:
        data = await EquipmentService.update_equipment(
            session=session,
            equipment_id=equipment_id,
            payload=payload.model_dump(exclude_unset=True),
            tenant_scope=tenant_scope,
            actor=username,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_EQUIPMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_EQUIPMENT,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.post(
    "/{equipment_id}/components",
    response_model=ManagerEquipmentComponentItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT_COMPONENT,
)
async def create_manager_equipment_component(
    equipment_id: int,
    payload: ManagerEquipmentComponentCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create a component on customer equipment, optionally referencing a shared catalog
    product and supplier. Missing equipment returns 404 and invalid references/type returns
    400. Partners cannot submit supplier/invoice fields, including explicit null (403). This
    stores component metadata without creating a new catalog product; repeated POSTs can
    create additional components.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    component_payload = payload.model_dump(exclude_unset=True)
    try:
        ManagerEquipmentPermissionService.assert_supplier_fields_allowed(
            payload=component_payload,
            tenant_scope=tenant_scope,
        )
        data = await EquipmentService.create_component(
            session=session,
            equipment_id=equipment_id,
            payload=component_payload,
            tenant_scope=tenant_scope,
        )
    except TenantEquipmentCommercialFieldsDeniedError as exc:
        raise manager_http_error(
            status_code=403,
            endpoint=CREATE_MANAGER_EQUIPMENT_COMPONENT,
            error_code=FORBIDDEN,
            message=str(exc),
        ) from exc
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT_COMPONENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_EQUIPMENT_COMPONENT,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.patch(
    "/{equipment_id}/components/{component_id}",
    response_model=ManagerEquipmentComponentItemResponse,
    operation_id=PATCH_MANAGER_EQUIPMENT_COMPONENT,
)
async def patch_manager_equipment_component(
    equipment_id: int,
    component_id: int,
    payload: ManagerEquipmentComponentUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Update only submitted component fields; explicit null can clear nullable
    product/supplier references and is_archived controls archival. Missing
    equipment/component returns 404 and invalid references/type returns 400.
    Supplier/invoice fields are system-only (partner submissions return 403). No
    expected-version guard or idempotency receipt is used.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    component_payload = payload.model_dump(exclude_unset=True)
    try:
        ManagerEquipmentPermissionService.assert_supplier_fields_allowed(
            payload=component_payload,
            tenant_scope=tenant_scope,
        )
        data = await EquipmentService.update_component(
            session=session,
            equipment_id=equipment_id,
            component_id=component_id,
            payload=component_payload,
            tenant_scope=tenant_scope,
        )
    except TenantEquipmentCommercialFieldsDeniedError as exc:
        raise manager_http_error(
            status_code=403,
            endpoint=PATCH_MANAGER_EQUIPMENT_COMPONENT,
            error_code=FORBIDDEN,
            message=str(exc),
        ) from exc
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_EQUIPMENT_COMPONENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_EQUIPMENT_COMPONENT,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.get(
    "/{equipment_id}/history",
    response_model=ManagerEquipmentServiceHistoryListResponse,
    operation_id=LIST_MANAGER_EQUIPMENT_HISTORY,
)
async def list_manager_equipment_history(
    equipment_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read service-history events for customer equipment with page starting at 1 and limit
    1–100. Missing or inaccessible equipment returns 404. Events record completed work;
    reading them does not advance maintenance dates or generate orders.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [equipment and
    maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    data = await EquipmentService.list_history(
        session=session,
        equipment_id=equipment_id,
        page=page,
        limit=limit,
        tenant_scope=tenant_scope,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=LIST_MANAGER_EQUIPMENT_HISTORY,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.post(
    "/{equipment_id}/history",
    response_model=ManagerEquipmentServiceHistoryItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT_HISTORY,
)
async def create_manager_equipment_history(
    equipment_id: int,
    payload: ManagerEquipmentServiceHistoryCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Record a completed service event on equipment, validating any linked order against the
    same customer/branch. Missing equipment returns 404 and invalid event/order/provider
    data returns 400. A maintenance event updates warranty maintenance status; repairs and
    diagnostics do not advance the independent maintenance schedule. No idempotency receipt
    exists, so repeats create separate events.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [equipment and
    maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    try:
        data = await EquipmentService.add_history(
            session=session,
            equipment_id=equipment_id,
            payload=payload.model_dump(exclude_unset=True),
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT_HISTORY,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_EQUIPMENT_HISTORY,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.post(
    "/{equipment_id}/history/from-repair-order",
    response_model=ManagerEquipmentServiceHistoryItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT_HISTORY_FROM_REPAIR_ORDER,
)
async def create_manager_equipment_history_from_repair_order(
    equipment_id: int,
    payload: ManagerEquipmentHistoryFromRepairOrderPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Synchronize the equipment repair-history entry from one scoped repair order under an
    order lock. A repeat updates the existing order-derived entry rather than adding
    another, preserving manual overrides omitted from the payload. Missing equipment returns
    404; invalid repair order, association or conflicting existing history returns 400. This
    records repair history rather than an actual maintenance event.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [equipment and
    maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
    """
    try:
        data = await EquipmentService.add_history_from_repair_order(
            session=session,
            equipment_id=equipment_id,
            payload=payload.model_dump(exclude_unset=True),
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT_HISTORY_FROM_REPAIR_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_EQUIPMENT_HISTORY_FROM_REPAIR_ORDER,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data
