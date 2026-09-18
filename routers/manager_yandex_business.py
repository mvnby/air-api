from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.yandex_business import (
    YandexBusinessFeedPreview,
    YandexBusinessFeedQualityReport,
    YandexBusinessFeedSettingsPayload,
    YandexBusinessFeedSettingsResponse,
)
from core.database import get_session
from core.security import get_current_owner_username, get_current_username
from routers.manager_operation_ids import (
    GET_MANAGER_YANDEX_BUSINESS_FEED_SETTINGS,
    GET_MANAGER_YANDEX_BUSINESS_PRICE_LIST,
    GET_MANAGER_YANDEX_BUSINESS_QUALITY_REPORT,
    PREVIEW_MANAGER_YANDEX_BUSINESS_FEED_SETTINGS,
    UPDATE_MANAGER_YANDEX_BUSINESS_FEED_SETTINGS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from services.tenant_scope_service import SystemTenantScopeResolver
from services.yandex_business_feed_settings_service import (
    YandexBusinessFeedConfiguration,
    YandexBusinessFeedSettingsService,
)
from services.yandex_business_price_list_service import YandexBusinessPriceListService


router = APIRouter(
    prefix="/api/manager/yandex-business",
    tags=["manager/yandex-business"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


def _configuration(payload: YandexBusinessFeedSettingsPayload) -> YandexBusinessFeedConfiguration:
    return YandexBusinessFeedConfiguration(**payload.model_dump())


def _settings_response(
    configuration: YandexBusinessFeedConfiguration,
) -> YandexBusinessFeedSettingsResponse:
    return YandexBusinessFeedSettingsResponse(**configuration.__dict__)


@router.get(
    "/settings",
    operation_id=GET_MANAGER_YANDEX_BUSINESS_FEED_SETTINGS,
    response_model=YandexBusinessFeedSettingsResponse,
)
async def get_manager_yandex_business_feed_settings(
    session: AsyncSession = Depends(get_session),
) -> YandexBusinessFeedSettingsResponse:
    tenant_scope = await SystemTenantScopeResolver.resolve(session)
    return _settings_response(
        await YandexBusinessFeedSettingsService.get(session, tenant_scope=tenant_scope)
    )


@router.post(
    "/settings/preview",
    operation_id=PREVIEW_MANAGER_YANDEX_BUSINESS_FEED_SETTINGS,
    response_model=YandexBusinessFeedPreview,
)
async def preview_manager_yandex_business_feed_settings(
    payload: YandexBusinessFeedSettingsPayload,
    session: AsyncSession = Depends(get_session),
) -> YandexBusinessFeedPreview:
    configuration = _configuration(payload)
    report = await YandexBusinessPriceListService.preview_quality_report(
        session,
        configuration=configuration,
    )
    return YandexBusinessFeedPreview(
        **report.model_dump(),
        settings=_settings_response(configuration),
    )


@router.put(
    "/settings",
    operation_id=UPDATE_MANAGER_YANDEX_BUSINESS_FEED_SETTINGS,
    response_model=YandexBusinessFeedSettingsResponse,
)
async def update_manager_yandex_business_feed_settings(
    payload: YandexBusinessFeedSettingsPayload,
    session: AsyncSession = Depends(get_session),
    _owner_username: str = Depends(get_current_owner_username),
) -> YandexBusinessFeedSettingsResponse:
    tenant_scope = await SystemTenantScopeResolver.resolve(session)
    configuration = await YandexBusinessFeedSettingsService.update(
        session,
        tenant_scope=tenant_scope,
        configuration=_configuration(payload),
    )
    return _settings_response(configuration)


@router.get(
    "/price-list.yml",
    operation_id=GET_MANAGER_YANDEX_BUSINESS_PRICE_LIST,
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/xml": {"schema": {"type": "string"}},
            }
        }
    },
)
async def get_manager_yandex_business_price_list(
    session: AsyncSession = Depends(get_session),
):
    content = await YandexBusinessPriceListService.build_xml(session)
    filename = quote("yandex-business-price-list.yml")
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        },
    )


@router.get(
    "/quality-report",
    operation_id=GET_MANAGER_YANDEX_BUSINESS_QUALITY_REPORT,
    response_model=YandexBusinessFeedQualityReport,
)
async def get_manager_yandex_business_quality_report(
    session: AsyncSession = Depends(get_session),
) -> YandexBusinessFeedQualityReport:
    return await YandexBusinessPriceListService.build_quality_report(session)
