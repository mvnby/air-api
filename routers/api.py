"""
API Router: Product endpoints.
Uses Service Layer with Dependency Injection for session management.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from core.database import get_session
from services.product_service import ProductService
from models import Product
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