import pytest
from sqlmodel import select

from core.config import settings
from models import Product
from models.supplier import SupplierOffer


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_supplier_sync_and_mapping_flow(async_client, db, monkeypatch):
    headers = await _auth_headers(async_client)

    class FakeGoogleService:
        def read_sheet_values(self, spreadsheet_id: str, **kwargs):
            return [
                ["sku", "title", "wholesale", "currency", "rrc", "qty"],
                ["SKU-1", "Split AC", "479", "USD", "2670", "5"],
            ]

    from services import supplier_sync_service

    monkeypatch.setattr(supplier_sync_service, "get_google_service", lambda: FakeGoogleService())

    create_supplier = await async_client.post(
        "/api/manager/suppliers",
        headers=headers,
        json={"name": "Test Supplier", "code": "test-sup", "priority": 1, "is_active": True},
    )
    assert create_supplier.status_code == 200
    supplier_id = create_supplier.json()["id"]

    create_source = await async_client.post(
        "/api/manager/supplier-sources",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "spreadsheet_id": "sheet1",
            "sheet_name": "Prices",
            "header_row_index": 1,
            "col_external_id": "A",
            "col_title": "B",
            "col_wholesale": "C",
            "col_wholesale_currency": "D",
            "col_rrc_byn": "E",
            "col_qty": "F",
        },
    )
    assert create_source.status_code == 200
    source_id = create_source.json()["id"]

    sync_resp = await async_client.post(
        f"/api/manager/supplier-sources/{source_id}/sync",
        headers=headers,
    )
    assert sync_resp.status_code == 200
    assert sync_resp.json()["rows_upserted"] == 1

    product = Product(title="Mapped AC", slug="mapped-ac", price=3000, area=25)
    db.add(product)
    await db.commit()
    await db.refresh(product)

    create_mapping = await async_client.post(
        "/api/manager/supplier-mappings",
        headers=headers,
        json={"product_id": product.id, "supplier_id": supplier_id, "external_id": "SKU-1"},
    )
    assert create_mapping.status_code == 200

    local_stock = await async_client.put(
        f"/api/manager/products/{product.id}/local-stock",
        headers=headers,
        json={"qty": 3},
    )
    assert local_stock.status_code == 200
    assert local_stock.json()["qty"] == 3

    list_products = await async_client.get("/api/manager/products/list", headers=headers)
    assert list_products.status_code == 200
    item = next(i for i in list_products.json()["items"] if i["id"] == product.id)
    assert item["vitebsk_qty"] == 3
    assert item["minsk_qty"] == 5
    assert item["availability_status"] == "in_stock_now"
    assert item["recommended_price_byn"] == 2670.0

    offer_res = await db.execute(select(SupplierOffer).where(SupplierOffer.external_id == "SKU-1"))
    offer = offer_res.scalar_one_or_none()
    assert offer is not None
