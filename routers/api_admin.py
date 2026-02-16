"""Admin/search/health endpoints split from the main API router."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from core.database import get_session
from core.security import get_current_username
from services.admin_api_service import AdminApiService
from services.product_service import ProductService

router = APIRouter(tags=["api"])


@router.get("/products/search")
async def search_products(
    q: str = None,
    is_inverter: bool = None,
    session: AsyncSession = Depends(get_session),
):
    """Search products with fuzzy matching."""
    products = await ProductService.search(session, query=q, is_inverter=is_inverter)
    return {"items": products}


@router.get("/admin/tags/filterable")
async def get_filterable_tags(
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    return await AdminApiService.get_filterable_tags(session)


@router.get("/admin/products/search")
async def admin_search_products(
    q: str = "",
    tag_ids: List[int] = Query(None),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    return await AdminApiService.search_products(session, q=q, tag_ids=tag_ids)


@router.get("/admin/services/search")
async def admin_search_services(
    q: str = "",
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    return await AdminApiService.search_services(session, q=q)


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_session)):
    """Check API and database availability."""
    return await AdminApiService.health_check(session)
