"""Public product/catalog endpoints split from the main API router."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.database import get_session
from core.security import get_current_username
from crud.product import ProductDAO
from models import Product
from schemas import (
    CatalogResponse,
    FiltersConfigResponse,
    Meta,
    ProductImageResponse,
    ProductResponse,
    ProductSiblingResponse,
    SpecsKeysResponse,
    TagGroupResponse,
    TagResponse,
)
from services.description_generator import DescriptionGeneratorService
from services.product_serialization import parse_legacy_images, sanitize_specs
from services.product_service import ProductService

router = APIRouter(tags=["api"])


def _map_product_to_response(
    product: Product,
    series_siblings: Optional[List[Product]] = None,
) -> ProductResponse:
    p_tags = []
    if product.tags:
        for tag in product.tags:
            group = None
            if tag.group:
                group = TagGroupResponse(
                    title=tag.group.title,
                    slug=tag.group.slug,
                    is_public=tag.group.is_public,
                )
            p_tags.append(
                TagResponse(
                    id=tag.id,
                    title=tag.title,
                    slug=tag.slug,
                    is_public=tag.is_public,
                    sort_order=tag.sort_order,
                    group=group,
                    group_title=tag.group.title if tag.group else None,
                )
            )

    specs = sanitize_specs(product.specs)
    images = parse_legacy_images(product.images)

    gallery = []
    if product.gallery_images:
        for img in product.gallery_images:
            gallery.append(
                ProductImageResponse(
                    id=img.id,
                    url=img.url,
                    is_installation_photo=img.is_installation_photo,
                )
            )

    siblings_payload = [
        ProductSiblingResponse(
            id=item.id,
            title=item.title,
            slug=item.slug,
            price=item.price,
            old_price=item.old_price,
            area=item.area,
            is_inverter=item.is_inverter,
            main_image=item.main_image,
        )
        for item in (series_siblings or [])
    ]

    return ProductResponse(
        id=product.id,
        title=product.title,
        slug=product.slug,
        price=product.price,
        old_price=product.old_price,
        area=product.area,
        is_inverter=product.is_inverter,
        power_cooling=product.power_cooling,
        main_image=product.main_image,
        is_published=product.is_published,
        created_at=product.created_at,
        tags=p_tags,
        specs=specs or {},
        images=images or [],
        gallery_images=gallery,
        series_siblings=siblings_payload,
    )


def _validate_pagination(page: int, limit: int) -> None:
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 1000")


@router.get("/v1/specs/keys", response_model=SpecsKeysResponse, operation_id="get_public_spec_keys")
async def get_public_spec_keys(session: AsyncSession = Depends(get_session)):
    stmt = select(Product.specs)
    result = await session.execute(stmt)
    all_specs = result.scalars().all()

    stats = {}
    for spec_dict in all_specs:
        if spec_dict:
            for key in spec_dict.keys():
                if str(key).startswith("__"):
                    continue
                stats[key] = stats.get(key, 0) + 1

    return SpecsKeysResponse(keys=sorted(stats.keys()), total_products_using=stats)


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
    tag_slugs: Optional[List[str]] = Query(None),
    is_inverter: Optional[bool] = None,
    session: AsyncSession = Depends(get_session),
):
    _validate_pagination(page, limit)

    faceted_tag_ids = None
    if tag_slugs:
        faceted_tag_ids = await ProductService.resolve_slugs_to_grouped_ids(session, tag_slugs)

    items = await ProductDAO.get_filtered(
        session,
        area_min=area_min,
        area_max=area_max,
        min_price=min_price,
        max_price=max_price,
        heating_min=heating_min,
        has_wifi=has_wifi,
        is_inverter=is_inverter,
        tag_slugs=None,
        faceted_tag_ids=faceted_tag_ids,
        sort=sort,
        page=page,
        limit=limit,
        is_published=True,
    )
    total = await ProductDAO.count_filtered(
        session,
        area_min=area_min,
        area_max=area_max,
        min_price=min_price,
        max_price=max_price,
        heating_min=heating_min,
        has_wifi=has_wifi,
        is_inverter=is_inverter,
        tag_slugs=None,
        faceted_tag_ids=faceted_tag_ids,
        is_published=True,
    )

    pages = (total + limit - 1) // limit if limit > 0 else 0
    return CatalogResponse(
        items=[_map_product_to_response(product) for product in items],
        meta=Meta(total=total, page=page, limit=limit, pages=pages),
    )


@router.get("/v1/products/{identifier}", response_model=ProductResponse, operation_id="get_product")
async def get_product_by_identifier(identifier: str, session: AsyncSession = Depends(get_session)):
    product = await ProductService.get_product_by_identifier(session, identifier)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product with identifier '{identifier}' not found")
    siblings = await ProductService.get_series_siblings(session, product, limit=8)
    return _map_product_to_response(product, series_siblings=siblings)
