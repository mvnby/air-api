"""Public product/catalog endpoints split from the main API router."""

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from core.tenant_scope import get_public_tenant_scope, verify_public_storefront_request
from models.tenancy import TenantScope
from schemas import (
    CatalogResponse,
    FiltersConfigResponse,
    Meta,
    ProductSeriesNavigationResponse,
    ProductResponse,
    SpecsKeysResponse,
    SpecRegistryResponse,
)
from services.description_generator import DescriptionGeneratorService
from services.product_response_mapper import map_product_to_response
from services.product_service import ProductService
from services.feature_resolver_service import FeatureResolverService
from services.public_catalog_service import PublicCatalogService

router = APIRouter(tags=["api"])
_PUBLIC_STOREFRONT_DEPENDENCIES = [Depends(verify_public_storefront_request)]


@router.get(
    "/v1/specs/keys",
    response_model=SpecsKeysResponse,
    operation_id="get_public_spec_keys",
    dependencies=_PUBLIC_STOREFRONT_DEPENDENCIES,
)
async def get_public_spec_keys(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    payload = await PublicCatalogService.get_public_spec_keys(
        session,
        tenant_scope=tenant_scope,
    )
    return SpecsKeysResponse(**payload)


@router.get(
    "/v1/specs/registry",
    response_model=SpecRegistryResponse,
    operation_id="get_public_spec_registry",
    dependencies=_PUBLIC_STOREFRONT_DEPENDENCIES,
)
async def get_public_spec_registry():
    payload = ProductService.get_specs_registry()
    return SpecRegistryResponse(**payload)


@router.get(
    "/v1/filters/config",
    response_model=FiltersConfigResponse,
    operation_id="get_filters_config",
    dependencies=_PUBLIC_STOREFRONT_DEPENDENCIES,
)
async def get_filters_config(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    return await PublicCatalogService.get_filters_config(
        session,
        tenant_scope=tenant_scope,
    )


@router.post("/products/{product_id}/generate-description")
async def generate_product_description(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    text = await DescriptionGeneratorService.generate(session, product_id)
    return {"description": text}


@router.get(
    "/v1/catalog",
    response_model=CatalogResponse,
    operation_id="get_products",
    dependencies=_PUBLIC_STOREFRONT_DEPENDENCIES,
)
@router.get(
    "/v1/products",
    response_model=CatalogResponse,
    operation_id="get_products_v1",
    dependencies=_PUBLIC_STOREFRONT_DEPENDENCIES,
)
async def get_catalog(
    page: int = 1,
    limit: int = 20,
    sort: str = "recommended",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    area_min: Optional[int] = None,
    area_max: Optional[int] = None,
    heating_min: Optional[int] = None,
    has_wifi: Optional[bool] = None,
    has_fresh_air: Optional[bool] = None,
    color: Optional[Literal["black"]] = Query(
        None,
        description="Canonical indoor unit color family",
    ),
    indoor_types: Optional[List[str]] = Query(
        None,
        description="Indoor unit types for semi-industrial catalog (duct/cassette/floor_ceiling/column)",
    ),
    tag_slugs: Optional[List[str]] = Query(None),
    brand_slugs: Optional[List[str]] = Query(None, description="Canonical brand slugs to include"),
    is_inverter: Optional[bool] = None,
    q: Optional[str] = Query(None, description="Smart search query"),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    try:
        ProductService.validate_public_pagination(page, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = await PublicCatalogService.get_catalog_page(
        session,
        tenant_scope=tenant_scope,
        page=page,
        limit=limit,
        sort=sort,
        min_price=min_price,
        max_price=max_price,
        area_min=area_min,
        area_max=area_max,
        heating_min=heating_min,
        has_wifi=has_wifi,
        has_fresh_air=has_fresh_air,
        color=color,
        indoor_types=indoor_types,
        tag_slugs=tag_slugs,
        brand_slugs=brand_slugs,
        is_inverter=is_inverter,
        search=q,
    )
    products = [projection.product for projection in payload["items"]]
    supply_metrics = await ProductService.get_supply_metrics_map(session, products)
    await FeatureResolverService.resolve_for_products(session, products)

    return CatalogResponse(
        items=[
            map_product_to_response(
                projection,
                supply_metrics=supply_metrics.get(projection.product.id),
            )
            for projection in payload["items"]
        ],
        meta=Meta(**payload["meta"]),
    )


@router.get(
    "/v1/products/vitebsk-featured",
    response_model=List[ProductResponse],
    operation_id="get_vitebsk_featured_products",
    dependencies=_PUBLIC_STOREFRONT_DEPENDENCIES,
)
async def get_vitebsk_featured_products(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    projections = await PublicCatalogService.get_vitebsk_featured_products(
        session,
        tenant_scope=tenant_scope,
        limit=6,
    )
    products = [projection.product for projection in projections]
    supply_metrics = await ProductService.get_supply_metrics_map(session, products)
    await FeatureResolverService.resolve_for_products(session, products)
    return [
        map_product_to_response(
            projection,
            supply_metrics=supply_metrics.get(projection.product.id),
        )
        for projection in projections
    ]


@router.get(
    "/v1/product-series/navigation",
    response_model=ProductSeriesNavigationResponse,
    operation_id="get_product_series_navigation",
    dependencies=_PUBLIC_STOREFRONT_DEPENDENCIES,
)
async def get_product_series_navigation(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    return await PublicCatalogService.get_series_navigation(
        session,
        tenant_scope=tenant_scope,
    )


@router.get(
    "/v1/products/{identifier}",
    response_model=ProductResponse,
    operation_id="get_product",
    dependencies=_PUBLIC_STOREFRONT_DEPENDENCIES,
)
async def get_product_by_identifier(
    identifier: str,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_public_tenant_scope),
):
    page = await PublicCatalogService.get_product_page(
        session,
        tenant_scope=tenant_scope,
        identifier=identifier,
    )
    if not page:
        raise HTTPException(status_code=404, detail=f"Product with identifier '{identifier}' not found")
    product = page.product.product
    siblings = [projection.product for projection in page.siblings]
    supply_metrics = await ProductService.get_supply_metrics_map(session, [product])
    await FeatureResolverService.resolve_for_products(session, [product])
    return map_product_to_response(
        page.product,
        series_siblings=page.siblings,
        supply_metrics=supply_metrics.get(product.id),
    )
