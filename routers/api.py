"""
API Router: Product endpoints.
Uses Service Layer with Dependency Injection for session management.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select, and_, func
from typing import List, Optional

from core.database import get_session
from services.product_service import ProductService
from models import Product, Tag, TagGroup, ProductTagLink
from services.description_generator import DescriptionGeneratorService

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/products")
async def get_products(session: AsyncSession = Depends(get_session)):
    """Get all published products."""
    products = await ProductService.get_all(session)
    return {"items": products}


@router.get("/products/{product_id}")
async def get_product(product_id: int, session: AsyncSession = Depends(get_session)):
    """Get a single product by ID."""
    product = await ProductService.get_by_id(session, product_id)
    return product


@router.get("/products/search")
async def search_products(
    q: str = None,
    is_inverter: bool = None,
    session: AsyncSession = Depends(get_session)
):
    """Search products with fuzzy matching."""
    products = await ProductService.search(session, query=q, is_inverter=is_inverter)
    return {"items": products}

@router.get("/admin/tags/filterable")
async def get_filterable_tags(session: AsyncSession = Depends(get_session)):
    stmt = (
        select(TagGroup, Tag)
        .join(Tag, Tag.group_id == TagGroup.id)
        .where(Tag.is_filter == True)
        .order_by(TagGroup.sort_order, TagGroup.title, Tag.sort_order, Tag.title)
    )
    result = await session.execute(stmt)
    
    grouped = {}
    for row in result:
        group, tag = row
        if group.title not in grouped:
            grouped[group.title] = {
                "group_label": group.title,
                "tags": []
            }
        grouped[group.title]["tags"].append({
            "id": tag.id,
            "title": tag.title,
            "slug": tag.slug
        })
    
    return list(grouped.values())

# ADMIN SEARCH ENDPOINTS (for Select2)
@router.get("/admin/products/search")
async def admin_search_products(
    q: str = "", 
    tag_ids: List[int] = Query(None),
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Product)
    
    # 1. Фильтрация по тегам (AND логика)
    if tag_ids:
        # Для AND логики: продукт должен иметь связь со ВСЕМИ указанными тегами
        tag_subquery = (
            select(ProductTagLink.product_id)
            .where(ProductTagLink.tag_id.in_(tag_ids))
            .group_by(ProductTagLink.product_id)
            .having(func.count(ProductTagLink.tag_id) == len(tag_ids))
        )
        stmt = stmt.where(Product.id.in_(tag_subquery))
    
    # 2. Поиск по тексту (в названии или описании)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            (Product.title.ilike(pattern)) | (Product.description.ilike(pattern))
        )
    
    stmt = stmt.limit(20)
    result = await session.execute(stmt)
    products = result.scalars().all()
    return [{"id": p.id, "text": p.title, "price": p.price} for p in products]

@router.get("/admin/services/search")
async def admin_search_services(q: str = "", session: AsyncSession = Depends(get_session)):
    from models import Service
    stmt = select(Service).where(Service.title.ilike(f"%{q}%")).limit(20)
    result = await session.execute(stmt)
    services = result.scalars().all()
    return [{"id": s.id, "text": s.title, "price": s.base_price} for s in services]


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_session)):
    """Check API and database availability."""
    try:
        await session.execute(select(1))
        return {"status": "ok", "database": "online"}
    except Exception as e:
        return {"status": "error", "database": "offline", "detail": str(e)}

@router.post("/products/{product_id}/generate-description")
async def generate_product_description(
    product_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Генерирует описание на основе тегов и возвращает текст.
    Админ может потом его отредактировать и сохранить.
    """
    text = await DescriptionGeneratorService.generate(session, product_id)
    return {"description": text}