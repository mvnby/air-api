from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from services.yandex_business_price_list_service import YandexBusinessPriceListService


router = APIRouter(tags=["api"])


@router.get(
    "/v1/feeds/yandex-business.yml",
    operation_id="get_yandex_business_feed",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/xml": {"schema": {"type": "string"}},
            }
        }
    },
)
async def get_yandex_business_feed(
    session: AsyncSession = Depends(get_session),
):
    content = await YandexBusinessPriceListService.build_xml(session)
    return Response(content=content, media_type="application/xml; charset=utf-8")
