from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.yandex_business import YandexBusinessFeedQualityReport
from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    GET_MANAGER_YANDEX_BUSINESS_PRICE_LIST,
    GET_MANAGER_YANDEX_BUSINESS_QUALITY_REPORT,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from services.yandex_business_price_list_service import YandexBusinessPriceListService


router = APIRouter(
    prefix="/api/manager/yandex-business",
    tags=["manager/yandex-business"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


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
