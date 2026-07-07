"""Public content/service/config endpoints split from the main API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from core.database import get_session
from schemas import ArticleResponse, PublicBrandDetailResponse, PublicBrandResponse, ServiceResponse
from services.article_service import ArticleService
from services.content_api_service import ContentApiService
from services.installation_service import InstallationService

router = APIRouter(tags=["api"])


@router.get("/v1/content/articles", response_model=List[ArticleResponse])
async def get_articles(session: AsyncSession = Depends(get_session)):
    """Get list of published articles ordered by creation date (newest first)."""
    return await ArticleService.get_all_published(session)


@router.get("/v1/content/articles/{slug}", response_model=ArticleResponse)
async def get_article(slug: str, session: AsyncSession = Depends(get_session)):
    """Get article details by slug. Returns 404 if not found or not published."""
    article = await ArticleService.get_by_slug(session, slug)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article with slug '{slug}' not found")
    return article


@router.get("/v1/content/services", response_model=List[ServiceResponse])
async def get_services(session: AsyncSession = Depends(get_session)):
    """Get list of all available services."""
    return await ContentApiService.get_active_services(session)


@router.get("/v1/content/brands", response_model=List[PublicBrandResponse], operation_id="get_public_brands")
async def get_public_brands(session: AsyncSession = Depends(get_session)):
    """Get published brands that have at least one published product."""
    return await ContentApiService.get_public_brands(session)


@router.get(
    "/v1/content/brands/{slug}",
    response_model=PublicBrandDetailResponse,
    operation_id="get_public_brand",
)
async def get_public_brand(slug: str, session: AsyncSession = Depends(get_session)):
    """Get a published brand by slug if it has published products."""
    brand = await ContentApiService.get_public_brand_by_slug(session, slug)
    if not brand:
        raise HTTPException(status_code=404, detail=f"Brand with slug '{slug}' not found")
    return brand


@router.get("/v1/services/options", response_model=List[ServiceResponse])
async def get_service_options(
    category: str = "installation_option",
    session: AsyncSession = Depends(get_session),
):
    """Get rich installation options."""
    return await ContentApiService.get_service_options(session, category=category)


@router.get("/v1/installation-rates")
async def get_installation_rates(session: AsyncSession = Depends(get_session)):
    """Get all installation rates."""
    return await InstallationService.get_all(session)


@router.get("/v1/config", operation_id="get_config")
async def get_global_config(session: AsyncSession = Depends(get_session)):
    """
    Get all global configuration parameters as a key-value dictionary.
    Example: {"phone": "+37529...", "email": "..."}
    """
    return await ContentApiService.get_global_config_map(session)
