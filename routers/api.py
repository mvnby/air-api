from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_session
from models import Product

router = APIRouter(prefix="/api", tags=["api"])

@router.get("/products")
async def get_products(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Product))
    products = result.scalars().all()
    return {"items": products}

@router.get("/products/{product_id}")
async def get_product(product_id: int, session: AsyncSession = Depends(get_session)):
    product = await session.get(Product, product_id)
    return product
