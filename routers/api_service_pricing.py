"""Public, read-only tenant service tariff and calculation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.tenant_scope import get_public_tenant_scope, verify_public_storefront_request
from models import ServiceTariff
from models.tenancy import TenantScope
from schemas import ManagerInstallEstimateCalculatePayload, ManagerInstallEstimateResponse, ManagerTariffServiceKind
from schemas_service_catalog import (
    PublicServiceEstimateCalculatePayload,
    PublicServiceTariffListResponse,
    PublicServiceTariffResponse,
    PublicServiceTariffRuleResponse,
)
from services.service_estimate_service import ServiceEstimateService
from services.storefront_settings_service import StorefrontSettingsService
from services.tariffs_service import TariffsService
from services.installation_price_book_service import InstallationPriceBookService
from schemas_installation_price_book import (
    InstallationResolvePayload, InstallationResolveResponse,
    InstallationPreviewPayload, InstallationPreviewResponse,
    InstallationPricingConfigResponse,
)
from services.public_installation_pricing_bridge_service import PublicInstallationPricingBridgeService
from core.storefront_request_envelope import private_storefront_response_headers
from core.public_write_idempotency import get_required_public_write_idempotency_key


router = APIRouter(
    prefix="/v1/service-pricing",
    tags=["api/service-pricing"],
    dependencies=[Depends(verify_public_storefront_request)],
)


def _book_preview_required() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "book_preview_required", "message": "Use the published installation price book preview"},
        headers=private_storefront_response_headers(),
    )


@router.get(
    "/installation/config",
    response_model=InstallationPricingConfigResponse,
    operation_id="get_public_installation_pricing_config",
)
async def get_public_installation_pricing_config(
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Tell the storefront which installation pricing contract is authoritative. Response uses
    private/no-store headers; read this before choosing legacy calculation or price-book
    preview.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    response.headers.update(private_storefront_response_headers())
    return await PublicInstallationPricingBridgeService.config(session, tenant_scope)


@router.post(
    "/installation/resolve",
    response_model=InstallationResolveResponse,
    operation_id="resolve_public_installation_tariff",
)
async def resolve_public_installation_tariff(
    payload: InstallationResolvePayload,
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Resolve a tariff using the storefront installation price book. Disabled installation is
    reported as status=unavailable with service_direction_not_enabled, rather than 404. Does
    not create an order.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    response.headers.update(private_storefront_response_headers())
    if not await StorefrontSettingsService.is_service_enabled(
        session, tenant_scope=tenant_scope, service_kind="installation"
    ):
        return InstallationResolveResponse(status="unavailable", reason_code="service_direction_not_enabled",
                                           scope_ref=InstallationPriceBookService._scope_ref(tenant_scope))
    result, _ = await InstallationPriceBookService.resolve(session, tenant_scope, payload)
    return result


@router.post(
    "/installation/preview",
    response_model=InstallationPreviewResponse,
    operation_id="preview_public_installation_estimate",
)
async def preview_public_installation_estimate(
    payload: InstallationPreviewPayload,
    response: Response,
    idempotency_key: str = Depends(get_required_public_write_idempotency_key),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Calculate a price-book installation preview and, outside read-only demo scope, persist
    its receipt using the required Idempotency-Key. Public callers cannot approve site
    access: approved_site_access returns 422. Disabled installation returns
    status=unavailable. A persistent preview replays the same input/key for its 30-minute
    receipt lifetime; another input with that key returns 409 idempotency_key_reused. A
    price-book revision mismatch returns 409 price_changed. Receipt
    contention/unavailability can return 503 with Retry-After: 1; retain the same input/key
    for a retry. Preview is not acceptance or order creation.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    response.headers.update(private_storefront_response_headers())
    if payload.approved_site_access:
        raise HTTPException(status_code=422, detail={"code": "site_access_approval_manager_only"})
    if not await StorefrontSettingsService.is_service_enabled(
        session, tenant_scope=tenant_scope, service_kind="installation"
    ):
        return InstallationPreviewResponse(status="unavailable", reason_code="service_direction_not_enabled",
                                           scope_ref=InstallationPriceBookService._scope_ref(tenant_scope))
    return await InstallationPriceBookService.preview(
        session, tenant_scope, payload,
        idempotency_key=idempotency_key, persist=not tenant_scope.demo_read_only,
    )


def _public_tariff(tariff: ServiceTariff) -> PublicServiceTariffResponse:
    rules = sorted(
        [rule for rule in list(tariff.rules or []) if rule.is_active],
        key=lambda rule: (rule.sort_order, rule.id or 0),
    )
    return PublicServiceTariffResponse(
        id=int(tariff.id),
        service_kind=ManagerTariffServiceKind(tariff.service_kind),
        short_name=tariff.effective_short_name,
        full_description=(tariff.full_description or "").strip() or None,
        category=tariff.category,
        power_range=tariff.power_range,
        base_price=int(tariff.base_price or 0),
        included_route_meters=float(tariff.included_route_meters or 0),
        rules=[PublicServiceTariffRuleResponse.model_validate(rule) for rule in rules],
    )


async def _require_enabled(
    session: AsyncSession,
    *,
    tenant_scope: TenantScope,
    service_kind: str,
) -> None:
    if not await StorefrontSettingsService.is_service_enabled(
        session,
        tenant_scope=tenant_scope,
        service_kind=service_kind,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "service_direction_not_enabled",
                "message": "Service direction is unavailable",
            },
        )


@router.get(
    "/tariffs",
    response_model=PublicServiceTariffListResponse,
    operation_id="list_public_service_tariffs",
)
async def list_public_service_tariffs(
    service_kind: ManagerTariffServiceKind = Query(...),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    List active service tariffs and active rules for this storefront and service direction.
    Disabled direction returns 404; installation backed by a published price book returns
    409 book_preview_required.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    await _require_enabled(
        session,
        tenant_scope=tenant_scope,
        service_kind=service_kind.value,
    )
    if service_kind == ManagerTariffServiceKind.installation and await InstallationPriceBookService.latest(session, tenant_scope):
        raise _book_preview_required()
    tariffs = await TariffsService.get_all_tariffs(
        session,
        service_kind=service_kind,
        include_inactive=False,
        tenant_scope=tenant_scope,
    )
    return PublicServiceTariffListResponse(
        items=[_public_tariff(tariff) for tariff in tariffs]
    )


@router.post(
    "/calculate",
    response_model=ManagerInstallEstimateResponse,
    operation_id="calculate_public_service_tariff",
)
async def calculate_public_service_tariff(
    payload: PublicServiceEstimateCalculatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Calculate a legacy active tariff within this storefront without creating an order.
    Disabled service direction returns 404; installation with a published price book returns
    409 book_preview_required. Tariff access and active status are checked by the tariff
    service.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    tariff = await TariffsService.get_tariff_by_id(
        session,
        payload.tariff_id,
        tenant_scope,
        require_active=True,
    )
    await _require_enabled(
        session,
        tenant_scope=tenant_scope,
        service_kind=tariff.service_kind,
    )
    if tariff.service_kind == ManagerTariffServiceKind.installation.value and await InstallationPriceBookService.latest(session, tenant_scope):
        raise _book_preview_required()
    manager_payload = ManagerInstallEstimateCalculatePayload(
        **payload.model_dump(),
        discount_amount=0,
    )
    return await ServiceEstimateService.calculate_install_estimate(
        session,
        manager_payload,
        tenant_scope,
    )
