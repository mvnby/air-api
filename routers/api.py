from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_session
from models import Product

router = APIRouter(prefix="/api", tags=["api"])

@router.get("/products")
async def get_products(session: AsyncSession = Depends(get_session)):
    # Load categories eagerly to include them in the response (as objects)
    from sqlalchemy.orm import selectinload
    result = await session.execute(select(Product).options(selectinload(Product.categories)))
    products = result.scalars().all()
    return {"items": products}

@router.get("/products/{product_id}")
async def get_product(product_id: int, session: AsyncSession = Depends(get_session)):
    from sqlalchemy.orm import selectinload
    result = await session.execute(select(Product).where(Product.id == product_id).options(selectinload(Product.categories)))
    product = result.scalar_one_or_none()
    return product
