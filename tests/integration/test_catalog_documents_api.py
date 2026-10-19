import pytest
from io import BytesIO
from pypdf import PdfWriter

from core.config import settings
from core.security import AuthenticatedUser, get_current_auth_context
from models import Brand, Product, ProductAttachment, ProductSeries
from models.catalog_document import CatalogDocument
from services.catalog_revision_service import CatalogRevisionService


async def _seed(db):
    brand = Brand(title="Knowledge", slug="knowledge-brand")
    db.add(brand)
    await db.flush()
    series = ProductSeries(brand_id=brand.id, title="FG", slug="knowledge-fg")
    db.add(series)
    await db.flush()
    product = Product(brand_id=brand.id, series_id=series.id, title="Knowledge model", slug="knowledge-model", price=1000)
    db.add(product)
    await db.commit()
    return brand, series, product


async def _owner_headers(client):
    login = await client.post("/login/access-token", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_catalog_documents_manager_replace_noop_validation_and_inherited_origin(async_client, db):
    brand, series, product = await _seed(db)
    headers = await _owner_headers(async_client)
    db.add(CatalogDocument(brand_id=brand.id, title="Brand catalog", kind="catalog", url="https://example.com/catalog.pdf"))
    await db.commit()
    path = f"/api/manager/catalog-documents/series/{series.id}"
    before = await CatalogRevisionService.get_current(db)
    payload = {"documents": [{"title": "Operation", "kind": "operation", "url": "https://example.com/operation.pdf", "source_url": "https://example.com/source", "language": "ru", "year": 2026}]}
    saved = await async_client.put(path, headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["own"][0]["origin_id"] == series.id
    assert saved.json()["inherited"][0]["origin_id"] == brand.id
    after = await CatalogRevisionService.get_current(db)
    assert after["revision"] == before["revision"] + 1
    unchanged = await async_client.put(path, headers=headers, json=payload)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["own"][0]["id"] == saved.json()["own"][0]["id"]
    assert await CatalogRevisionService.get_current(db) == after
    invalid = await async_client.put(path, headers=headers, json={"documents": [{"title": "Unsafe", "url": "http://127.0.0.1/private.pdf"}]})
    assert invalid.status_code == 422
    duplicate = await async_client.put(path, headers=headers, json={"documents": [payload["documents"][0], payload["documents"][0]]})
    assert duplicate.status_code == 400
    assert await CatalogRevisionService.get_current(db) == after
    cleared = await async_client.put(path, headers=headers, json={"documents": []})
    assert cleared.status_code == 200
    assert cleared.json()["own"] == []
    assert len(cleared.json()["inherited"]) == 1
    missing = await async_client.get("/api/manager/catalog-documents/series/987654321", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_catalog_documents_enforce_editor_permission_for_internal_sources_and_upload(async_client, db):
    from main import app

    brand, series, product = await _seed(db)
    path = f"/api/manager/catalog-documents/series/{series.id}"
    unauthenticated = await async_client.get(path)
    assert unauthenticated.status_code == 401
    async def reader():
        return AuthenticatedUser(username="reader", auth_source="test", role="manager", tenant_id=1, storefront_id=1)
    app.dependency_overrides[get_current_auth_context] = reader
    try:
        assert (await async_client.get(path)).status_code == 403
        assert (await async_client.put(path, json={"documents": []})).status_code == 403
        assert (await async_client.post(f"{path}/upload", files={"file": ("Manual.pdf", b"%PDF-1.7", "application/pdf")})).status_code == 403
        async def editor():
            return AuthenticatedUser(username="editor", auth_source="test", role="catalog_editor", tenant_id=1, storefront_id=1, permissions=("catalog.master.edit",))
        app.dependency_overrides[get_current_auth_context] = editor
        allowed = await async_client.put(path, json={"documents": [{"title": "PRIVATE research", "url": "https://example.com/private.pdf", "visibility": "internal"}]})
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["own"][0]["visibility"] == "internal"
        assert (await async_client.get(path)).status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_auth_context, None)


@pytest.mark.asyncio
async def test_catalog_documents_public_upload_is_attached_only_on_save(async_client, db, tmp_path, monkeypatch):
    brand, series, product = await _seed(db)
    headers = await _owner_headers(async_client)
    monkeypatch.setenv("MEDIA_LOCAL_DIR", str(tmp_path))
    monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "local")
    path = f"/api/manager/catalog-documents/series/{series.id}"
    before = await CatalogRevisionService.get_current(db)
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(output)
    content = output.getvalue()
    uploaded = await async_client.post(f"{path}/upload", headers=headers, files={"file": ("Operation.pdf", content, "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["url"].startswith("/media/catalog-documents/original/")
    stored = list(tmp_path.rglob("*.pdf"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == content
    assert await CatalogRevisionService.get_current(db) == before
    empty = await async_client.get(path, headers=headers)
    assert empty.json()["own"] == []
    saved = await async_client.put(path, headers=headers, json={"documents": [{**uploaded.json(), "kind": "operation"}]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["own"][0]["url"] == uploaded.json()["url"]


@pytest.mark.asyncio
async def test_catalog_documents_public_product_brand_series_and_legacy_manual_contract(async_client, db):
    brand, series, product = await _seed(db)
    db.add_all([
        CatalogDocument(brand_id=brand.id, title="Brand catalog", kind="catalog", url="https://example.com/catalog.pdf"),
        CatalogDocument(series_id=series.id, title="Operation", kind="operation", url="https://example.com/manual.pdf", source_url="https://example.com/PRIVATE-provenance"),
        CatalogDocument(series_id=series.id, title="Operation 2", kind="operation", url="https://example.com/manual-2.pdf"),
        CatalogDocument(series_id=series.id, title="PRIVATE service", kind="service", url="https://example.com/PRIVATE-service.pdf", visibility="internal"),
        ProductAttachment(product_id=product.id, title="Legacy operation", kind="manual", url="https://example.com/manual.pdf"),
    ])
    await db.commit()
    response = await async_client.get(f"/api/v1/products/{product.slug}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["url"] for item in payload["documents"]] == ["https://example.com/manual.pdf", "https://example.com/manual-2.pdf", "https://example.com/catalog.pdf"]
    assert [item["url"] for item in payload["manuals"]] == ["https://example.com/manual.pdf", "https://example.com/manual-2.pdf"]
    assert payload["documents"][0]["origin_type"] == "series"
    assert payload["documents"][0]["origin_title"] == "FG"
    assert "PRIVATE" not in response.text
    assert len(payload["series"]["documents"]) == 3
    brand_page = await async_client.get(f"/api/v1/content/brands/{brand.slug}")
    assert brand_page.status_code == 200, brand_page.text
    assert [item["url"] for item in brand_page.json()["documents"]] == ["https://example.com/catalog.pdf"]
    series_page = await async_client.get(f"/api/v1/content/brands/{brand.slug}/series/{series.slug}")
    assert series_page.status_code == 200, series_page.text
    assert len(series_page.json()["series"]["documents"]) == 3
    assert "PRIVATE" not in series_page.text


@pytest.mark.asyncio
async def test_private_model_document_suppresses_ancestor_url_in_entire_product_response(async_client, db):
    brand, series, product = await _seed(db)
    excluded_url = "https://example.com/model-excluded-operation.pdf"
    allowed_url = "https://example.com/allowed-operation.pdf"
    db.add_all([
        CatalogDocument(brand_id=brand.id, title="Brand operation", kind="operation", url=excluded_url),
        CatalogDocument(series_id=series.id, title="Series operation", kind="operation", url=excluded_url),
        CatalogDocument(series_id=series.id, title="Other operation", kind="operation", url=allowed_url),
        CatalogDocument(product_id=product.id, title="Private model exception", kind="operation", url=excluded_url, visibility="internal"),
    ])
    await db.commit()

    response = await async_client.get(f"/api/v1/products/{product.slug}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["url"] for item in payload["documents"]] == [allowed_url]
    assert [item["url"] for item in payload["manuals"]] == [allowed_url]
    assert [item["url"] for item in payload["series"]["documents"]] == [allowed_url]
    assert excluded_url not in response.text
    assert "Private model exception" not in response.text

    # The model exception is contextual and does not hide the series' own public page.
    series_page = await async_client.get(f"/api/v1/content/brands/{brand.slug}/series/{series.slug}")
    assert series_page.status_code == 200, series_page.text
    assert {item["url"] for item in series_page.json()["series"]["documents"]} == {excluded_url, allowed_url}
