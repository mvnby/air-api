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
)
from core.storefront_request_envelope import private_storefront_response_headers


router = APIRouter(
    prefix="/v1/service-pricing",
    tags=["api/service-pricing"],
    dependencies=[Depends(verify_public_storefront_request)],
)


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
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    response.headers.update(private_storefront_response_headers())
    if not await StorefrontSettingsService.is_service_enabled(
        session, tenant_scope=tenant_scope, service_kind="installation"
    ):
        return InstallationPreviewResponse(status="unavailable", reason_code="service_direction_not_enabled",
                                           scope_ref=InstallationPriceBookService._scope_ref(tenant_scope))
    return await InstallationPriceBookService.preview(session, tenant_scope, payload)


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
    await _require_enabled(
        session,
        tenant_scope=tenant_scope,
        service_kind=service_kind.value,
    )
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
    manager_payload = ManagerInstallEstimateCalculatePayload(
        **payload.model_dump(),
        discount_amount=0,
    )
    return await ServiceEstimateService.calculate_install_estimate(
        session,
        manager_payload,
        tenant_scope,
    )
