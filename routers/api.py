from fastapi import APIRouter, Depends
from sqlmodel import select, Session
from database import get_session
from models import Product

router = APIRouter(prefix="/api", tags=["api"])

@router.get("/products")
def get_products(session: Session = Depends(get_session)):
    products = session.exec(select(Product)).all()
    return {"items": products}

@router.get("/products/{product_id}")
def get_product(product_id: int, session: Session = Depends(get_session)):
    product = session.get(Product, product_id)
    return product
