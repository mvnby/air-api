from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import GET_MANAGER_YANDEX_BUSINESS_PRICE_LIST
from services.yandex_business_price_list_service import YandexBusinessPriceListService


router = APIRouter(
    prefix="/api/manager/yandex-business",
    tags=["manager/yandex-business"],
    dependencies=[Depends(get_current_username)],
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
    site_base_url: str = Query(
        "https://mvn.by",
        description="Public storefront base URL for product and image links",
    ),
    session: AsyncSession = Depends(get_session),
):
    content = await YandexBusinessPriceListService.build_xml(
        session=session,
        site_base_url=site_base_url,
    )
    filename = quote("yandex-business-price-list.yml")
    return Response(
        content=content,
        media_type="application/xml; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        },
    )
