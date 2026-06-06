"""Public catalog revision endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from schemas import CatalogRevisionResponse
from services.catalog_revision_service import CatalogRevisionService


router = APIRouter(tags=["api"])


@router.get(
    "/v1/catalog/revision",
    response_model=CatalogRevisionResponse,
    operation_id="get_catalog_revision",
)
async def get_catalog_revision(session: AsyncSession = Depends(get_session)):
    return await CatalogRevisionService.get_current(session)
