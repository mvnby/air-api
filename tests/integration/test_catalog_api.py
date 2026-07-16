import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta
from models import Brand, Product, ProductImage, ProductImageVariant
from crud.supplier import ProductLocalStockDAO
from services.product_image_processing_contract import (
    ProductImageManualQualityStatus,
    ProductImageProcessingStatus,
    ProductImageVariantType,
)
from services.spec_normalizer import normalize_specs

@pytest.fixture
async def seed_product(db):
    """Seed a test product for catalog tests."""
    product = Product(
        title="Integration Test Product",
        slug="integration-test-product",
        price=1000,
        area=25,
        is_published=True
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product

@pytest.mark.asyncio
async def test_list_products(async_client: AsyncClient, seed_product):
    """Test fetching the product catalog."""
    response = await async_client.get("/api/v1/products")
    
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    
    # Verify seeded product is in the list
    slugs = [item["slug"] for item in data["items"]]
    assert seed_product.slug in slugs


@pytest.mark.asyncio
async def test_public_catalog_rejects_limit_above_100(async_client: AsyncClient):
    response = await async_client.get("/api/v1/catalog", params={"limit": 101})

    assert response.status_code == 400
    assert response.json()["detail"] == "Limit must be between 1 and 100"

@pytest.mark.asyncio
async def test_product_detail(async_client: AsyncClient, seed_product):
    """Test fetching a specific product by slug."""
    response = await async_client.get(f"/api/v1/products/{seed_product.slug}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == seed_product.id
    assert data["title"] == seed_product.title
    assert data["slug"] == seed_product.slug


@pytest.mark.asyncio
async def test_public_product_detail_includes_canonical_brand(async_client: AsyncClient, db):
    brand = Brand(
        title="Haier",
        slug="haier",
        logo_url="/media/brands/haier.svg",
        is_published=True,
    )
    db.add(brand)
    await db.flush()

    product = Product(
        title="Haier Brand Detail Product",
        slug="haier-brand-detail-product",
        price=1200,
        area=25,
        brand_id=brand.id,
        is_published=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    response = await async_client.get(f"/api/v1/products/{product.slug}")

    assert response.status_code == 200, response.text
    assert response.json()["brand"] == {
        "id": brand.id,
        "title": "Haier",
        "slug": "haier",
        "logo_url": "/media/brands/haier.svg",
    }


@pytest.mark.asyncio
async def test_public_product_detail_hides_unpublished_slug(async_client: AsyncClient, db):
    product = Product(
        title="Hidden Detail Product",
        slug="hidden-detail-product",
        price=1000,
        area=25,
        is_published=False,
    )
    db.add(product)
    await db.commit()

    response = await async_client.get(f"/api/v1/products/{product.slug}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_public_product_detail_hides_unpublished_id(async_client: AsyncClient, db):
    product = Product(
        title="Hidden Detail Product By ID",
        slug="hidden-detail-product-by-id",
        price=1000,
        area=25,
        is_published=False,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    response = await async_client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_public_product_payload_exposes_approved_ready_image_variants(async_client: AsyncClient, db):
    product = Product(
        title="Approved Variant Product",
        slug="approved-variant-product",
        price=1500,
        area=25,
        is_published=True,
        main_image="/media/products/source.webp",
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    image = ProductImage(
        product_id=product.id,
        url="/media/products/source.webp",
        is_installation_photo=False,
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)

    db.add_all(
        [
            ProductImageVariant(
                product_image_id=image.id,
                variant_type=ProductImageVariantType.CARD.value,
                url="/media/products/variants/card/source.webp",
                processing_status=ProductImageProcessingStatus.READY.value,
                manual_quality_status=ProductImageManualQualityStatus.APPROVED.value,
            ),
            ProductImageVariant(
                product_image_id=image.id,
                variant_type=ProductImageVariantType.FULL.value,
                url="/media/products/variants/full/source.webp",
                processing_status=ProductImageProcessingStatus.READY.value,
                manual_quality_status=ProductImageManualQualityStatus.APPROVED.value,
            ),
        ]
    )
    await db.commit()

    catalog_response = await async_client.get("/api/v1/products", params={"limit": 20})
    assert catalog_response.status_code == 200, catalog_response.text
    catalog_item = next(
        item
        for item in catalog_response.json()["items"]
        if item["slug"] == product.slug
    )
    assert catalog_item["main_image"] == "/media/products/source.webp"
    assert catalog_item["card_image"] == "/media/products/variants/card/source.webp"
    assert catalog_item["full_image"] == "/media/products/variants/full/source.webp"

    detail_response = await async_client.get(f"/api/v1/products/{product.slug}")
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["main_image"] == "/media/products/source.webp"
    assert detail["card_image"] == "/media/products/variants/card/source.webp"
    assert detail["full_image"] == "/media/products/variants/full/source.webp"
    assert detail["gallery_images"][0]["url"] == "/media/products/source.webp"
    assert detail["gallery_images"][0]["card_variant_url"] == "/media/products/variants/card/source.webp"
    assert detail["gallery_images"][0]["full_variant_url"] == "/media/products/variants/full/source.webp"

@pytest.mark.asyncio
async def test_product_not_found(async_client: AsyncClient):
    """Test fetching a non-existent product."""
    response = await async_client.get("/api/v1/products/non-existent-slug-12345")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_public_product_search_returns_items_from_smart_search(async_client: AsyncClient, db):
    marker = "PUBLICSEARCHSMART123"
    product = Product(
        title=f"{marker} Smart Search Product",
        slug=f"{marker.lower()}-smart-search-product",
        price=1234,
        area=25,
        is_inverter=True,
        is_published=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    response = await async_client.get("/api/products/search", params={"q": marker, "is_inverter": True})

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert any(item["id"] == product.id for item in items)


@pytest.mark.asyncio
async def test_public_catalog_search_count_matches_filtered_items(async_client: AsyncClient, db):
    marker = "CATALOGCOUNTSEARCH987"
    matching_products = [
        Product(
            title=f"{marker} Product {index}",
            slug=f"{marker.lower()}-product-{index}",
            price=1200 + index,
            area=25,
            is_published=True,
        )
        for index in range(2)
    ]
    db.add_all(
        [
            *matching_products,
            Product(
                title="Unrelated catalog count product",
                slug="unrelated-catalog-count-product",
                price=999,
                area=20,
                is_published=True,
            ),
        ]
    )
    await db.commit()

    response = await async_client.get(
        "/api/v1/catalog",
        params={"q": marker, "limit": 1},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["meta"] == {
        "total": 2,
        "page": 1,
        "limit": 1,
        "pages": 2,
    }


@pytest.mark.asyncio
async def test_catalog_default_sort_uses_recommendation_score(async_client: AsyncClient, db):
    now = datetime.now()
    apartment = Product(
        title="Apartment in stock",
        slug="apartment-in-stock",
        price=1500,
        area=25,
        is_published=True,
        created_at=now - timedelta(days=3),
    )
    mid_area = Product(
        title="Mid area in stock",
        slug="mid-area-in-stock",
        price=1700,
        area=35,
        is_published=True,
        created_at=now - timedelta(days=2),
    )
    large_area = Product(
        title="Large area in stock",
        slug="large-area-in-stock",
        price=2200,
        area=50,
        is_published=True,
        created_at=now - timedelta(days=1),
    )
    unavailable_new = Product(
        title="Unavailable new",
        slug="unavailable-new",
        price=1200,
        area=20,
        is_published=True,
        created_at=now,
    )
    db.add_all([apartment, mid_area, large_area, unavailable_new])
    await db.commit()

    for product in (apartment, mid_area, large_area):
        await ProductLocalStockDAO.upsert(
            session=db,
            product_id=product.id,
            qty=1,
            updated_by="test",
            warehouse_code="vitebsk",
        )

    response = await async_client.get("/api/v1/products?limit=4")
    assert response.status_code == 200
    slugs = [item["slug"] for item in response.json()["items"]]
    assert slugs == [
        "apartment-in-stock",
        "mid-area-in-stock",
        "large-area-in-stock",
        "unavailable-new",
    ]

    response = await async_client.get("/api/v1/products?limit=4&area_max=50")
    assert response.status_code == 200
    slugs = [item["slug"] for item in response.json()["items"]]
    assert slugs[:3] == [
        "large-area-in-stock",
        "mid-area-in-stock",
        "apartment-in-stock",
    ]


@pytest.mark.asyncio
async def test_catalog_filters_by_wifi_and_heating(async_client: AsyncClient, db):
    good = Product(
        title="Good",
        slug="good",
        price=1000,
        area=35,
        is_inverter=True,
        is_published=True,
        specs=normalize_specs({"temp_range_heat": "от -25 до +24", "wifi_ready": "да"}),
    )
    weak = Product(
        title="Weak",
        slug="weak",
        price=1000,
        area=35,
        is_inverter=True,
        is_published=True,
        specs=normalize_specs({"temp_range_heat": "от -10 до +24", "wifi_ready": "нет"}),
    )
    db.add(good)
    db.add(weak)
    await db.commit()

    response = await async_client.get("/api/v1/products?has_wifi=true&heating_min=-20")
    assert response.status_code == 200
    payload = response.json()
    slugs = [item["slug"] for item in payload["items"]]
    assert "good" in slugs
    assert "weak" not in slugs
    assert all(not key.startswith("__") for key in payload["items"][0]["specs"].keys())


@pytest.mark.asyncio
async def test_catalog_filters_black_color_variants(async_client: AsyncClient, db):
    products = [
        Product(
            title="Black Cyrillic",
            slug="black-cyrillic",
            price=1000,
            area=25,
            is_published=True,
            specs=normalize_specs({"Цвет корпуса": "Черный"}),
        ),
        Product(
            title="Black English",
            slug="black-english",
            price=1100,
            area=25,
            is_published=True,
            specs=normalize_specs({"Цвет корпуса": "Black mirror"}),
        ),
        Product(
            title="Black Combined",
            slug="black-combined",
            price=1200,
            area=25,
            is_published=True,
            specs=normalize_specs({"Цвет корпуса": "зеркальный, чёрный"}),
        ),
        Product(
            title="Graphite",
            slug="graphite",
            price=1300,
            area=25,
            is_published=True,
            specs=normalize_specs({"Цвет корпуса": "Графит"}),
        ),
        Product(
            title="White",
            slug="white",
            price=900,
            area=25,
            is_published=True,
            specs=normalize_specs({"Цвет корпуса": "Белый"}),
        ),
    ]
    db.add_all(products)
    await db.commit()

    response = await async_client.get("/api/v1/catalog?color=black")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {item["slug"] for item in payload["items"]} == {
        "black-cyrillic",
        "black-english",
        "black-combined",
    }
    assert payload["meta"]["total"] == 3


@pytest.mark.asyncio
async def test_catalog_rejects_unknown_color(async_client: AsyncClient):
    response = await async_client.get("/api/v1/catalog?color=purple")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_catalog_filters_by_brand_entity_slug(async_client: AsyncClient, db):
    mdv = Brand(title="MDV", slug="mdv", is_published=True, sort_order=10)
    haier = Brand(title="Haier", slug="haier", is_published=True, sort_order=40)
    db.add_all([mdv, haier])
    await db.flush()

    db.add_all(
        [
            Product(title="MDV product", slug="mdv-product", price=1000, area=25, brand_id=mdv.id, is_published=True),
            Product(
                title="Haier product",
                slug="haier-product",
                price=1000,
                area=25,
                brand_id=haier.id,
                is_published=True,
            ),
        ]
    )
    await db.commit()

    response = await async_client.get("/api/v1/products?tag_slugs=mdv")
    assert response.status_code == 200
    slugs = [item["slug"] for item in response.json()["items"]]
    assert "mdv-product" in slugs
    assert "haier-product" not in slugs


@pytest.mark.asyncio
async def test_catalog_filters_by_explicit_brand_slugs(async_client: AsyncClient, db):
    mdv = Brand(title="MDV Explicit", slug="mdv-explicit", is_published=True, sort_order=10)
    haier = Brand(title="Haier Explicit", slug="haier-explicit", is_published=True, sort_order=40)
    db.add_all([mdv, haier])
    await db.flush()

    db.add_all(
        [
            Product(
                title="MDV explicit product",
                slug="mdv-explicit-product",
                price=1000,
                area=25,
                brand_id=mdv.id,
                is_published=True,
                specs={"brand": "Wrong free text"},
            ),
            Product(
                title="Haier explicit product",
                slug="haier-explicit-product",
                price=1000,
                area=25,
                brand_id=haier.id,
                is_published=True,
            ),
        ]
    )
    await db.commit()

    response = await async_client.get("/api/v1/catalog?brand_slugs=mdv-explicit")
    assert response.status_code == 200, response.text
    slugs = [item["slug"] for item in response.json()["items"]]
    assert "mdv-explicit-product" in slugs
    assert "haier-explicit-product" not in slugs


@pytest.mark.asyncio
async def test_catalog_filters_by_indoor_types(async_client: AsyncClient, db):
    cassette = Product(
        title="Cassette Unit",
        slug="cassette-unit",
        price=2100,
        area=80,
        is_published=True,
        specs=normalize_specs({"Тип внутреннего блока": "кассетный"}),
    )
    duct = Product(
        title="Duct Unit",
        slug="duct-unit",
        price=2300,
        area=90,
        is_published=True,
        specs=normalize_specs({"Тип внутреннего блока": "канальный"}),
    )
    db.add(cassette)
    db.add(duct)
    await db.commit()

    response = await async_client.get("/api/v1/products?indoor_types=cassette")
    assert response.status_code == 200
    payload = response.json()
    slugs = [item["slug"] for item in payload["items"]]
    assert "cassette-unit" in slugs
    assert "duct-unit" not in slugs
