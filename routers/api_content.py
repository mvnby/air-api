"""Public content/service/config endpoints split from the main API router."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from core.database import get_session
from core.tenant_scope import get_public_tenant_scope, verify_public_storefront_request
from models.tenancy import TenantScope
from schemas import (
    ArticleResponse,
    PublicBrandDetailResponse,
    PublicBrandResponse,
    PublicSeriesPageResponse,
    ServiceResponse,
)
from services.article_service import ArticleService
from services.content_api_service import ContentApiService
from services.installation_service import InstallationService
from services.installation_price_book_service import InstallationPriceBookService
from services.public_installation_pricing_bridge_service import PublicInstallationPricingBridgeService
from core.storefront_request_envelope import private_storefront_response_headers
from services.public_series_page_service import PublicSeriesPageService
from services.storefront_settings_service import StorefrontSettingsService

router = APIRouter(
    tags=["api"],
    dependencies=[Depends(verify_public_storefront_request)],
)


@router.get("/v1/content/articles", response_model=List[ArticleResponse])
async def get_articles(session: AsyncSession = Depends(get_session)):
    """
    List published articles, newest first. Articles are shared content: this handler does
    not apply tenant filtering to the article service.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    return await ArticleService.get_all_published(session)


@router.get("/v1/content/articles/{slug}", response_model=ArticleResponse)
async def get_article(slug: str, session: AsyncSession = Depends(get_session)):
    """
    Read one published shared article by slug. Missing or unpublished content returns 404;
    the article query is not tenant-scoped.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    article = await ArticleService.get_by_slug(session, slug)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article with slug '{slug}' not found")
    return article


@router.get("/v1/content/services", response_model=List[ServiceResponse])
async def get_services(
    response: Response,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Return storefront-visible service content through the installation pricing bridge, with
    private/no-store response headers.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    response.headers.update(private_storefront_response_headers())
    return await PublicInstallationPricingBridgeService.visible_content_services(
        session, tenant_scope,
    )


@router.get("/v1/content/brands", response_model=List[PublicBrandResponse], operation_id="get_public_brands")
async def get_public_brands(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    List published brands with products visible in the resolved storefront catalog.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    return await ContentApiService.get_public_brands(
        session,
        tenant_scope=tenant_scope,
    )


@router.get(
    "/v1/content/brands/{slug}",
    response_model=PublicBrandDetailResponse,
    operation_id="get_public_brand",
)
async def get_public_brand(
    slug: str,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Read a published brand by slug when it has products visible in this storefront. Missing
    or unavailable brands return 404.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    brand = await ContentApiService.get_public_brand_by_slug(
        session,
        slug,
        tenant_scope=tenant_scope,
    )
    if not brand:
        raise HTTPException(status_code=404, detail=f"Brand with slug '{slug}' not found")
    return brand


@router.get(
    "/v1/content/brands/{brand_slug}/series/{series_slug}",
    response_model=PublicSeriesPageResponse,
    operation_id="get_public_brand_series",
)
async def get_public_brand_series(
    brand_slug: str,
    series_slug: str,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Read a published brand series and its storefront-visible product cards. Missing or
    unavailable series return 404.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    payload = await PublicSeriesPageService.get_by_slugs(
        session,
        brand_slug=brand_slug,
        series_slug=series_slug,
        tenant_scope=tenant_scope,
    )
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Published series '{brand_slug}/{series_slug}' not found",
        )
    return payload


@router.get("/v1/services/options", response_model=List[ServiceResponse])
async def get_service_options(
    response: Response,
    category: str = "installation_option",
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Read legacy service options for the requested category in this storefront. Returns 409
    book_preview_required when the published price-book contract replaces that category; use
    the installation preview contract instead.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    response.headers.update(private_storefront_response_headers())
    if not await PublicInstallationPricingBridgeService.legacy_option_category_available(
        session, tenant_scope, category,
    ):
        raise HTTPException(status_code=409,
            detail={"code": "book_preview_required", "message": "Use the published installation price book preview"},
            headers=private_storefront_response_headers())
    return await ContentApiService.get_service_options(
        session,
        category=category,
        tenant_scope=tenant_scope,
    )


@router.get("/v1/installation-rates")
async def get_installation_rates(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Read legacy installation rates for this storefront. Disabled installation returns an
    empty list; an authoritative published price book returns 409 book_preview_required.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    if not await StorefrontSettingsService.is_service_enabled(
        session,
        tenant_scope=tenant_scope,
        service_kind="installation",
    ):
        return []
    if await InstallationPriceBookService.latest(session, tenant_scope):
        raise HTTPException(status_code=409,
            detail={"code": "book_preview_required", "message": "Use the published installation price book preview"},
            headers=private_storefront_response_headers())
    return await InstallationService.get_all(session, tenant_scope)


@router.get("/v1/config", operation_id="get_config")
async def get_global_config(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    """
    Return the public key/value configuration for the resolved storefront, not private
    platform settings.

    Access and scope: storefront context is resolved by the public gateway; tenant-aware
    operations use that storefront. Signed headers are verified outside OpenAPI. See
    [storefront
    authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
    """
    return await ContentApiService.get_global_config_map(
        session,
        tenant_scope=tenant_scope,
    )
