import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta

from models import Product
from crud.supplier import ProductLocalStockDAO


@pytest.mark.asyncio
async def test_vitebsk_featured_filters_by_stock_vitebsk_and_sorts(async_client: AsyncClient, db):
    now = datetime.now()

    older = Product(
        title="Older in stock",
        slug="older-in-stock",
        price=1000,
        area=25,
        is_published=True,
        created_at=now - timedelta(days=1),
    )
    newer = Product(
        title="Newer in stock",
        slug="newer-in-stock",
        price=1200,
        area=25,
        is_published=True,
        created_at=now,
    )
    out_of_stock = Product(
        title="Out of stock",
        slug="out-of-stock",
        price=1500,
        area=25,
        is_published=True,
        created_at=now + timedelta(hours=1),
    )

    db.add(older)
    db.add(newer)
    db.add(out_of_stock)
    await db.commit()

    # Insert ProductLocalStock records via DAO upsert (the endpoint joins and filters by this)
    await ProductLocalStockDAO.upsert(
        session=db,
        product_id=older.id,
        qty=2,
        updated_by="test",
        warehouse_code="vitebsk",
    )
    await ProductLocalStockDAO.upsert(
        session=db,
        product_id=newer.id,
        qty=5,
        updated_by="test",
        warehouse_code="vitebsk",
    )
    await ProductLocalStockDAO.upsert(
        session=db,
        product_id=out_of_stock.id,
        qty=0,
        updated_by="test",
        warehouse_code="vitebsk",
    )

    resp = await async_client.get("/api/v1/products/vitebsk-featured")
    assert resp.status_code == 200
    payload = resp.json()

    slugs = [item["slug"] for item in payload]
    assert "out-of-stock" not in slugs
    assert slugs[:2] == ["newer-in-stock", "older-in-stock"]

    # Sanity: all returned products must be marked in stock in payload
    for item in payload:
        assert item["vitebsk_qty"] > 0

