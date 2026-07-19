import pytest

from core.config import settings
from models import Product


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
        def extract_spreadsheet_id(self, value: str) -> str:
            return value

        def list_sheet_tabs(self, spreadsheet_id: str):
            return [{"title": "Prices", "index": 0, "sheet_id": 1}]

        def read_sheet_values(self, spreadsheet_id: str, **kwargs):
            return [
                ["sku", "title", "wholesale", "currency", "rrc", "qty", "url"],
                [
                    "SKU-1",
                    "Split AC MDSAG-09HRFN8",
                    "479",
                    "USD",
                    "2670",
                    "5",
                    "https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8",
                ],
            ]

    from services import supplier_mapping_service, supplier_sync_service

    monkeypatch.setattr(supplier_sync_service, "get_google_service", lambda: FakeGoogleService())
    monkeypatch.setattr(supplier_mapping_service, "get_google_service", lambda: FakeGoogleService())

    create_supplier = await async_client.post(
        "/api/manager/suppliers",
        headers=headers,
        json={"name": "Test Supplier", "priority": 1, "is_active": True, "spreadsheet_id_or_url": "sheet1"},
    )
    assert create_supplier.status_code == 200
    supplier_id = create_supplier.json()["id"]
    assert create_supplier.json()["spreadsheet_id"] == "sheet1"

    sheets_resp = await async_client.get(f"/api/manager/suppliers/{supplier_id}/sheets", headers=headers)
    assert sheets_resp.status_code == 200
    assert sheets_resp.json()["items"][0]["title"] == "Prices"

    create_source = await async_client.post(
        "/api/manager/supplier-sources",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "sheet_name": "Prices",
            "header_row_index": 1,
            "col_external_id": "A",
            "col_title": "B",
            "col_wholesale": "C",
            "col_wholesale_currency": "D",
            "col_rrc_byn": "E",
            "col_qty": "F",
            "col_source_url": "G",
        },
    )
    assert create_source.status_code == 200
    source_id = create_source.json()["id"]
    assert create_source.json()["col_source_url"] == "G"

    analysis_resp = await async_client.get(
        f"/api/manager/supplier-sources/{source_id}/analysis",
        headers=headers,
    )
    assert analysis_resp.status_code == 200
    analysis = analysis_resp.json()
    assert analysis["product_rows"] == 1
    assert analysis["url_rows"] == 1
    assert analysis["sample_rows"][1]["source_url"] == "https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8"

    sync_resp = await async_client.post(
        f"/api/manager/supplier-sources/{source_id}/sync",
        headers=headers,
    )
    assert sync_resp.status_code == 200
    assert sync_resp.json()["rows_upserted"] == 1

    sync_all = await async_client.post("/api/manager/supplier-sources/sync-all", headers=headers)
    assert sync_all.status_code == 200
    assert isinstance(sync_all.json(), list)

    unmapped_by_source = await async_client.get(
        "/api/manager/supplier-offers/unmapped",
        headers=headers,
        params={"source_id": source_id},
    )
    assert unmapped_by_source.status_code == 200
    assert len(unmapped_by_source.json()["items"]) >= 1
    offer_item = unmapped_by_source.json()["items"][0]
    assert offer_item["title_normalized"] == "split ac mdsag-09hrfn8"
    assert "MDSAG-09HRFN8" in offer_item["model_tokens"]
    assert offer_item["source_url"] == "https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8"

    import_candidates = await async_client.get(
        "/api/manager/supplier-offers/source-url-import-candidates",
        headers=headers,
        params={"source_id": source_id},
    )
    assert import_candidates.status_code == 200
    assert import_candidates.json()["items"][0]["source_url"] == "https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8"

    class FakeCatalogImportRuntime:
        def __init__(self):
            self.urls = []

        async def start_import(self, *, urls, with_related: bool, update_existing: bool):
            self.urls = urls
            assert with_related is False
            assert update_existing is False
            return {"job_id": "job-1", "status": "queued", "stage": "queued"}

    fake_runtime = FakeCatalogImportRuntime()
    from routers import manager_supply

    monkeypatch.setattr(manager_supply, "catalog_import_runtime_service", fake_runtime)

    start_import = await async_client.post(
        "/api/manager/supplier-offers/source-url-import",
        headers=headers,
        json={"urls": ["https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8"]},
    )
    assert start_import.status_code == 200
    assert start_import.json()["job_id"] == "job-1"
    assert fake_runtime.urls == ["https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8"]

    product = Product(
        title="Split AC MDSAG-09HRFN8",
        slug="mapped-ac",
        price=3000,
        specs={"area_m2": 25},
        source_url="https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8",
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    product_id = product.id

    import_candidates_after_product = await async_client.get(
        "/api/manager/supplier-offers/source-url-import-candidates",
        headers=headers,
        params={"source_id": source_id},
    )
    assert import_candidates_after_product.status_code == 200
    assert import_candidates_after_product.json()["items"] == []

    suggestions = await async_client.post(
        "/api/manager/supplier-offers/suggestions",
        headers=headers,
        json={
            "items": [{"supplier_id": supplier_id, "external_id": "SKU-1", "title_raw": "Split AC MDSAG-09HRFN8"}],
            "limit_per_offer": 5,
        },
    )
    assert suggestions.status_code == 200
    assert suggestions.json()["items"][0]["auto_eligible"] is True
    assert suggestions.json()["items"][0]["offer_tokens"] == ["MDSAG-09HRFN8"]
    candidate = suggestions.json()["items"][0]["candidates"][0]
    assert candidate["source_url"] == "https://catalog.onliner.by/conditioners/mdv/mdsag09hrfn8"
    assert "Совпала ссылка источника / Onliner" in candidate["explanations"]

    create_mapping = await async_client.post(
        "/api/manager/supplier-mappings",
        headers=headers,
        json={"product_id": product_id, "supplier_id": supplier_id, "external_id": "SKU-1"},
    )
    assert create_mapping.status_code == 200

    bulk_mapping = await async_client.post(
        "/api/manager/supplier-mappings/bulk",
        headers=headers,
        json={
            "items": [{"product_id": product_id, "supplier_id": supplier_id, "external_id": "SKU-1"}],
            "skip_conflicts": True,
        },
    )
    assert bulk_mapping.status_code == 200
    assert bulk_mapping.json()["skipped_count"] >= 1


@pytest.mark.asyncio
async def test_delete_last_source_hides_supplier_offers(async_client, monkeypatch):
    headers = await _auth_headers(async_client)

    class FakeGoogleService:
        def extract_spreadsheet_id(self, value: str) -> str:
            return value

        def list_sheet_tabs(self, spreadsheet_id: str):
            return [{"title": "Prices", "index": 0, "sheet_id": 1}]

        def read_sheet_values(self, spreadsheet_id: str, **kwargs):
            return [
                ["SKU-1", "Split AC", "479", "USD", "2670", "5"],
            ]

    from services import supplier_mapping_service, supplier_sync_service

    monkeypatch.setattr(supplier_sync_service, "get_google_service", lambda: FakeGoogleService())
    monkeypatch.setattr(supplier_mapping_service, "get_google_service", lambda: FakeGoogleService())

    create_supplier = await async_client.post(
        "/api/manager/suppliers",
        headers=headers,
        json={"name": "Delete Source Supplier", "priority": 1, "spreadsheet_id_or_url": "sheet-delete"},
    )
    assert create_supplier.status_code == 200
    supplier_id = create_supplier.json()["id"]

    create_source = await async_client.post(
        "/api/manager/supplier-sources",
        headers=headers,
        json={
            "supplier_id": supplier_id,
            "sheet_name": "Prices",
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

    sync_resp = await async_client.post(f"/api/manager/supplier-sources/{source_id}/sync", headers=headers)
    assert sync_resp.status_code == 200
    assert sync_resp.json()["rows_upserted"] == 1

    unmapped_before = await async_client.get(
        "/api/manager/supplier-offers/unmapped",
        headers=headers,
        params={"supplier_id": supplier_id},
    )
    assert unmapped_before.status_code == 200
    assert len(unmapped_before.json()["items"]) == 1

    delete_source = await async_client.delete(f"/api/manager/supplier-sources/{source_id}", headers=headers)
    assert delete_source.status_code == 200

    unmapped_after = await async_client.get(
        "/api/manager/supplier-offers/unmapped",
        headers=headers,
        params={"supplier_id": supplier_id},
    )
    assert unmapped_after.status_code == 200
    assert len(unmapped_after.json()["items"]) == 0
