import time

import pytest
from sqlmodel import select

from core.config import settings
from crud.supplier import ProductLocalStockDAO
from models import (
    Brand,
    Order,
    OrderProductLink,
    Product,
    ProductCollection,
    ProductCollectionItem,
    ProductCollectionPlacement,
    ProductSeries,
    ProductTagLink,
    Storefront,
    StorefrontDomain,
    Tag,
    TagGroup,
    TenantOffer,
)
from services.storefront_context_signature_service import (
    StorefrontContextSignatureService,
)


_SECRET = "test-public-catalog-secret-at-least-32-bytes"
_HOST = "orsha.catalog.test"


def _headers(path: str, *, method: str = "GET") -> dict[str, str]:
    timestamp = int(time.time())
    return {
        "X-MVN-Storefront-Host": _HOST,
        "X-MVN-Storefront-Timestamp": str(timestamp),
        "X-MVN-Storefront-Signature": StorefrontContextSignatureService.sign(
            secret=_SECRET,
            timestamp=timestamp,
            method=method,
            path=path,
            hostname=_HOST,
        ),
    }


async def _seed_catalog(db):
    storefront = Storefront(
        id=2,
        tenant_id=1,
        slug="orsha",
        display_name="MVN Орша",
        status="active",
        city="Орша",
        is_default=False,
    )
    db.add(storefront)
    await db.flush()
    db.add(
        StorefrontDomain(
            storefront_id=int(storefront.id),
            hostname=_HOST,
            status="active",
            is_primary=True,
        )
    )

    low_offer = Product(
        title="Offer low",
        slug="offer-low",
        price=9000,
        old_price=9500,
        specs={"area_m2": 25, "wifi": True},
        is_published=True,
    )
    high_offer = Product(
        title="Offer high",
        slug="offer-high",
        price=1000,
        specs={"area_m2": 35, "heating": True},
        is_published=True,
    )
    no_offer = Product(
        title="No offer",
        slug="no-offer",
        price=2000,
        specs={"area_m2": 50, "private_marker": True},
        is_published=True,
    )
    disabled_offer = Product(
        title="Disabled offer",
        slug="disabled-offer",
        price=2500,
        specs={"area_m2": 70},
        is_published=True,
    )
    globally_hidden = Product(
        title="Globally hidden",
        slug="globally-hidden-offer",
        price=500,
        specs={"area_m2": 20},
        is_published=False,
    )
    db.add_all([low_offer, high_offer, no_offer, disabled_offer, globally_hidden])
    await db.flush()
    db.add_all(
        [
            TenantOffer(
                tenant_id=1,
                storefront_id=2,
                product_id=int(low_offer.id),
                price=3000,
                old_price=3500,
                status="active",
                is_published=True,
                created_by_username="test",
                updated_by_username="test",
            ),
            TenantOffer(
                tenant_id=1,
                storefront_id=2,
                product_id=int(high_offer.id),
                price=7000,
                old_price=None,
                status="active",
                is_published=True,
                created_by_username="test",
                updated_by_username="test",
            ),
            TenantOffer(
                tenant_id=1,
                storefront_id=2,
                product_id=int(disabled_offer.id),
                price=4000,
                old_price=None,
                status="disabled",
                is_published=False,
                created_by_username="test",
                updated_by_username="test",
            ),
            TenantOffer(
                tenant_id=1,
                storefront_id=2,
                product_id=int(globally_hidden.id),
                price=600,
                old_price=None,
                status="active",
                is_published=True,
                created_by_username="test",
                updated_by_username="test",
            ),
        ]
    )
    await db.commit()
    return low_offer, high_offer, no_offer, disabled_offer


@pytest.mark.asyncio
async def test_secondary_storefront_catalog_is_offer_scoped_before_sort_and_pagination(
    async_client,
    db,
    monkeypatch,
):
    low_offer, high_offer, no_offer, disabled_offer = await _seed_catalog(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)
    path = "/api/v1/products"

    response = await async_client.get(
        path,
        params={"sort": "price_asc", "limit": 1, "page": 2},
        headers=_headers(path),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"] == {"total": 2, "page": 2, "limit": 1, "pages": 2}
    assert [item["slug"] for item in payload["items"]] == [high_offer.slug]
    assert payload["items"][0]["price"] == 7000
    assert no_offer.slug not in {item["slug"] for item in payload["items"]}
    assert disabled_offer.slug not in {item["slug"] for item in payload["items"]}

    first_page = await async_client.get(
        path,
        params={"sort": "price_asc", "limit": 1},
        headers=_headers(path),
    )
    assert first_page.status_code == 200, first_page.text
    assert first_page.json()["items"][0]["slug"] == low_offer.slug
    assert first_page.json()["items"][0]["price"] == 3000
    assert first_page.json()["items"][0]["old_price"] == 3500


@pytest.mark.asyncio
async def test_secondary_storefront_price_filter_uses_offer_price_in_sql(
    async_client,
    db,
    monkeypatch,
):
    low_offer, high_offer, _, _ = await _seed_catalog(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)
    path = "/api/v1/catalog"

    response = await async_client.get(
        path,
        params={"min_price": 5000, "max_price": 8000},
        headers=_headers(path),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["meta"]["total"] == 1
    assert [item["slug"] for item in payload["items"]] == [high_offer.slug]
    assert low_offer.slug not in {item["slug"] for item in payload["items"]}


@pytest.mark.asyncio
async def test_secondary_storefront_detail_denies_missing_offer_and_projects_price(
    async_client,
    db,
    monkeypatch,
):
    low_offer, _, no_offer, disabled_offer = await _seed_catalog(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)

    offered_path = f"/api/v1/products/{low_offer.slug}"
    offered = await async_client.get(offered_path, headers=_headers(offered_path))
    assert offered.status_code == 200, offered.text
    assert offered.json()["price"] == 3000
    assert offered.json()["old_price"] == 3500

    for hidden in (no_offer, disabled_offer):
        hidden_path = f"/api/v1/products/{hidden.slug}"
        response = await async_client.get(hidden_path, headers=_headers(hidden_path))
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_unsigned_canonical_catalog_keeps_shared_product_behavior(
    async_client,
    db,
):
    low_offer, _, no_offer, _ = await _seed_catalog(db)

    response = await async_client.get(
        "/api/v1/products",
        params={"sort": "price_asc", "limit": 100},
    )

    assert response.status_code == 200, response.text
    by_slug = {item["slug"]: item for item in response.json()["items"]}
    assert by_slug[low_offer.slug]["price"] == 9000
    assert by_slug[no_offer.slug]["price"] == 2000


@pytest.mark.asyncio
async def test_secondary_storefront_filters_and_specs_only_use_visible_offers(
    async_client,
    db,
    monkeypatch,
):
    low_offer, _, no_offer, _ = await _seed_catalog(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)
    expert_group = TagGroup(
        title="Экспертный выбор",
        slug="expert-badge",
        is_public=True,
        is_expert_badge=True,
    )
    db.add(expert_group)
    await db.flush()
    visible_tag = Tag(
        group_id=int(expert_group.id),
        title="Видимый",
        slug="visible-expert",
        is_public=True,
    )
    hidden_tag = Tag(
        group_id=int(expert_group.id),
        title="Скрытый",
        slug="hidden-expert",
        is_public=True,
    )
    db.add_all([visible_tag, hidden_tag])
    await db.flush()
    db.add_all(
        [
            ProductTagLink(product_id=int(low_offer.id), tag_id=int(visible_tag.id)),
            ProductTagLink(product_id=int(no_offer.id), tag_id=int(hidden_tag.id)),
        ]
    )
    await db.commit()

    filters_path = "/api/v1/filters/config"
    filters = await async_client.get(filters_path, headers=_headers(filters_path))
    assert filters.status_code == 200, filters.text
    assert filters.json()["price"] == {"min": 3000, "max": 7000}
    assert filters.json()["area"] == {"min": 25.0, "max": 35.0}
    assert [item["slug"] for item in filters.json()["expert_tags"]] == [
        visible_tag.slug
    ]

    specs_path = "/api/v1/specs/keys"
    specs = await async_client.get(specs_path, headers=_headers(specs_path))
    assert specs.status_code == 200, specs.text
    assert specs.json()["keys"] == ["area_m2", "heating", "wifi"]
    assert "private_marker" not in specs.json()["keys"]


@pytest.mark.asyncio
async def test_secondary_featured_products_require_visible_offer(
    async_client,
    db,
    monkeypatch,
):
    low_offer, _, no_offer, _ = await _seed_catalog(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)
    for product in (low_offer, no_offer):
        await ProductLocalStockDAO.upsert(
            session=db,
            product_id=int(product.id),
            qty=2,
            updated_by="test",
            warehouse_code="vitebsk",
        )

    path = "/api/v1/products/vitebsk-featured"
    response = await async_client.get(path, headers=_headers(path))

    assert response.status_code == 200, response.text
    assert [item["slug"] for item in response.json()] == [low_offer.slug]
    assert response.json()[0]["price"] == 3000


@pytest.mark.asyncio
async def test_all_public_product_surfaces_share_the_offer_boundary(
    async_client,
    db,
    monkeypatch,
):
    low_offer, high_offer, no_offer, _ = await _seed_catalog(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)

    visible_brand = Brand(
        title="Visible Brand",
        slug="visible-brand",
        is_published=True,
    )
    hidden_brand = Brand(
        title="Unoffered Brand",
        slug="unoffered-brand",
        is_published=True,
    )
    db.add_all([visible_brand, hidden_brand])
    await db.flush()
    series = ProductSeries(
        brand_id=int(visible_brand.id),
        title="Scoped Series",
        slug="scoped-series",
        is_published=True,
    )
    db.add(series)
    await db.flush()
    low_offer.brand_id = visible_brand.id
    low_offer.series_id = series.id
    low_offer.product_kind = "complete_split_system"
    low_offer.main_image = "/media/products/offer-low.webp"
    high_offer.brand_id = visible_brand.id
    high_offer.series_id = series.id
    no_offer.brand_id = hidden_brand.id
    no_offer.product_kind = "complete_split_system"
    no_offer.main_image = "/media/products/no-offer.webp"
    collection = ProductCollection(
        slug="scoped-collection",
        internal_name="Scoped collection",
        public_title="Scoped collection",
        status="published",
        mode="manual",
        min_items=1,
        max_items=6,
    )
    db.add(collection)
    await db.flush()
    db.add_all(
        [
            ProductCollectionItem(
                collection_id=int(collection.id),
                product_id=int(low_offer.id),
                position=0,
            ),
            ProductCollectionItem(
                collection_id=int(collection.id),
                product_id=int(no_offer.id),
                position=1,
            ),
            ProductCollectionPlacement(
                surface_key="home",
                slot_key="featured_products",
                collection_id=int(collection.id),
                position=0,
                is_enabled=True,
            ),
        ]
    )
    await db.commit()

    brands_path = "/api/v1/content/brands"
    brands = await async_client.get(brands_path, headers=_headers(brands_path))
    assert brands.status_code == 200, brands.text
    assert [item["slug"] for item in brands.json()] == [visible_brand.slug]
    assert brands.json()[0]["products_count"] == 2

    hidden_brand_path = f"/api/v1/content/brands/{hidden_brand.slug}"
    hidden_brand_response = await async_client.get(
        hidden_brand_path,
        headers=_headers(hidden_brand_path),
    )
    assert hidden_brand_response.status_code == 404

    series_path = (
        f"/api/v1/content/brands/{visible_brand.slug}/series/{series.slug}"
    )
    series_response = await async_client.get(
        series_path,
        headers=_headers(series_path),
    )
    assert series_response.status_code == 200, series_response.text
    assert {
        item["slug"]: item["price"]
        for item in series_response.json()["products"]
    } == {low_offer.slug: 3000, high_offer.slug: 7000}

    navigation_path = "/api/v1/product-series/navigation"
    navigation = await async_client.get(
        navigation_path,
        headers=_headers(navigation_path),
    )
    assert navigation.status_code == 200, navigation.text
    assert set(navigation.json()["products"]) == {low_offer.slug, high_offer.slug}
    assert navigation.json()["products"][low_offer.slug]["series_siblings"][0][
        "price"
    ] == 7000

    collection_path = (
        "/api/v1/content/placements/home/featured_products/collections"
    )
    collection_response = await async_client.get(
        collection_path,
        headers=_headers(collection_path),
    )
    assert collection_response.status_code == 200, collection_response.text
    items = collection_response.json()["collections"][0]["items"]
    assert [item["product"]["slug"] for item in items] == [low_offer.slug]
    assert items[0]["product"]["price"] == 3000

    search_path = "/api/products/search"
    hidden_search = await async_client.get(
        search_path,
        params={"q": "No offer"},
        headers=_headers(search_path),
    )
    assert hidden_search.status_code == 200, hidden_search.text
    assert hidden_search.json()["items"] == []

    visible_search = await async_client.get(
        search_path,
        params={"q": "Offer low"},
        headers=_headers(search_path),
    )
    assert visible_search.status_code == 200, visible_search.text
    assert visible_search.json()["items"][0]["slug"] == low_offer.slug
    assert visible_search.json()["items"][0]["price"] == 3000


@pytest.mark.asyncio
async def test_secondary_checkout_snapshots_offer_price_and_rejects_unoffered_product(
    async_client,
    db,
    monkeypatch,
):
    low_offer, _, no_offer, _ = await _seed_catalog(db)
    monkeypatch.setattr(settings, "STOREFRONT_CONTEXT_SIGNING_SECRET", _SECRET)
    path = "/api/v1/orders"
    customer = {
        "name": "Покупатель Орша",
        "phone": "+375291112233",
        "email": "orsha-catalog@example.test",
        "address": "Орша",
        "type": "individual",
    }

    created = await async_client.post(
        path,
        headers=_headers(path, method="POST"),
        json={
            "customer": customer,
            "items": [
                {
                    "product_id": low_offer.id,
                    "quantity": 2,
                    "with_installation": False,
                    "installation_options": [],
                }
            ],
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["total_amount"] == 6000
    order = await db.get(Order, created.json()["id"])
    assert order is not None
    assert order.technical_meta["public_catalog_pricing"]["items"] == [
        {
            "product_id": low_offer.id,
            "unit_price": 3000,
            "source": "tenant_offer",
        }
    ]
    link = (
        await db.execute(
            select(OrderProductLink).where(OrderProductLink.order_id == order.id)
        )
    ).scalar_one()
    assert link.price == 3000

    rejected = await async_client.post(
        path,
        headers=_headers(path, method="POST"),
        json={
            "customer": customer,
            "items": [
                {
                    "product_id": no_offer.id,
                    "quantity": 1,
                    "with_installation": False,
                    "installation_options": [],
                }
            ],
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "product_not_available"
