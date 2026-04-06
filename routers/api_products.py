"""Public product/catalog endpoints split from the main API router."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from schemas import (
    CatalogResponse,
    FiltersConfigResponse,
    Meta,
    ProductResponse,
    SpecsKeysResponse,
)
from services.description_generator import DescriptionGeneratorService
from services.catalog import CatalogService
from services.product_response_mapper import map_product_to_response
from services.product_service import ProductService

router = APIRouter(tags=["api"])


@router.get("/v1/specs/keys", response_model=SpecsKeysResponse, operation_id="get_public_spec_keys")
async def get_public_spec_keys(session: AsyncSession = Depends(get_session)):
    payload = await ProductService.get_public_spec_keys(session)
    return SpecsKeysResponse(**payload)


@router.get("/v1/filters/config", response_model=FiltersConfigResponse, operation_id="get_filters_config")
async def get_filters_config(session: AsyncSession = Depends(get_session)):
    return await ProductService.get_filters_config(session)


@router.post("/products/{product_id}/generate-description")
async def generate_product_description(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    text = await DescriptionGeneratorService.generate(session, product_id)
    return {"description": text}


@router.get("/v1/catalog", response_model=CatalogResponse, operation_id="get_products")
@router.get("/v1/products", response_model=CatalogResponse, operation_id="get_products_v1")
async def get_catalog(
    page: int = 1,
    limit: int = 20,
    sort: str = "newest",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    area_min: Optional[int] = None,
    area_max: Optional[int] = None,
    heating_min: Optional[int] = None,
    has_wifi: Optional[bool] = None,
    has_fresh_air: Optional[bool] = None,
    indoor_types: Optional[List[str]] = Query(
        None,
        description="Indoor unit types for semi-industrial catalog (duct/cassette/floor_ceiling/column)",
    ),
    tag_slugs: Optional[List[str]] = Query(None),
    is_inverter: Optional[bool] = None,
    q: Optional[str] = Query(None, description="Smart search query"),
    session: AsyncSession = Depends(get_session),
):
    try:
        ProductService.validate_public_pagination(page, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = await ProductService.get_catalog_page(
        session,
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
        indoor_types=indoor_types,
        tag_slugs=tag_slugs,
        is_inverter=is_inverter,
        search=q,
    )
    supply_metrics = await ProductService.get_supply_metrics_map(session, payload["items"])

    return CatalogResponse(
        items=[
            map_product_to_response(
                product,
                supply_metrics=supply_metrics.get(product.id),
            )
            for product in payload["items"]
        ],
        meta=Meta(**payload["meta"]),
    )


@router.get(
    "/v1/products/vitebsk-featured",
    response_model=List[ProductResponse],
    operation_id="get_vitebsk_featured_products",
)
async def get_vitebsk_featured_products(session: AsyncSession = Depends(get_session)):
    products = await CatalogService.get_vitebsk_featured_products(session, limit=6)
    supply_metrics = await ProductService.get_supply_metrics_map(session, products)
    return [
        map_product_to_response(
            product,
            supply_metrics=supply_metrics.get(product.id),
        )
        for product in products
    ]


@router.get("/v1/products/{identifier}", response_model=ProductResponse, operation_id="get_product")
async def get_product_by_identifier(identifier: str, session: AsyncSession = Depends(get_session)):
    product = await ProductService.get_product_by_identifier(session, identifier)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product with identifier '{identifier}' not found")
    siblings = await ProductService.get_series_siblings(session, product, limit=8)
    supply_metrics = await ProductService.get_supply_metrics_map(session, [product])
    return map_product_to_response(
        product,
        series_siblings=siblings,
        supply_metrics=supply_metrics.get(product.id),
    )
