"""Public content/service/config endpoints split from the main API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from typing import List

from core.database import get_session
from models import GlobalConfig, Service
from schemas import ArticleResponse, ServiceResponse

router = APIRouter(tags=["api"])


@router.get("/v1/content/articles", response_model=List[ArticleResponse])
async def get_articles(session: AsyncSession = Depends(get_session)):
    """Get list of published articles ordered by creation date (newest first)."""
    from services.article_service import ArticleService

    return await ArticleService.get_all_published(session)


@router.get("/v1/content/articles/{slug}", response_model=ArticleResponse)
async def get_article(slug: str, session: AsyncSession = Depends(get_session)):
    """Get article details by slug. Returns 404 if not found or not published."""
    from services.article_service import ArticleService

    article = await ArticleService.get_by_slug(session, slug)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article with slug '{slug}' not found")
    return article


@router.get("/v1/content/services", response_model=List[ServiceResponse])
async def get_services(session: AsyncSession = Depends(get_session)):
    """Get list of all available services."""
    stmt = select(Service).where(Service.is_active == True).order_by(Service.id)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/v1/services/options", response_model=List[ServiceResponse])
async def get_service_options(
    category: str = "installation_option",
    session: AsyncSession = Depends(get_session),
):
    """Get rich installation options."""
    stmt = (
        select(Service)
        .where(Service.is_active == True)
        .where(Service.category == category)
        .order_by(Service.base_price)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/v1/installation-rates")
async def get_installation_rates(session: AsyncSession = Depends(get_session)):
    """Get all installation rates."""
    from services.installation_service import InstallationService

    return await InstallationService.get_all(session)


@router.get("/v1/config", operation_id="get_config")
async def get_global_config(session: AsyncSession = Depends(get_session)):
    """
    Get all global configuration parameters as a key-value dictionary.
    Example: {"phone": "+37529...", "email": "..."}
    """
    stmt = select(GlobalConfig)
    result = await session.execute(stmt)
    configs = result.scalars().all()
    return {c.key: c.value for c in configs}
