from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

import pytest

from core.config import settings
from models import (
    Brand,
    Product,
    ProductCollection,
    ProductCollectionItem,
    ProductCollectionPlacement,
    ServiceTariff,
)
from services.yandex_business_price_list_service import YandexBusinessPriceListService


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _product(
    *,
    title: str,
    slug: str,
    brand: Brand | None = None,
    price: int = 1000,
    main_image: str | None = None,
    specs: dict | None = None,
) -> Product:
    return Product(
        title=title,
        slug=slug,
        description=f"<p>{title}</p>",
        price=price,
        main_image=main_image,
        specs=specs or {},
        is_published=True,
        brand=brand,
    )


def _collection(*, slug: str, title: str, min_items: int = 1, **kwargs) -> ProductCollection:
    return ProductCollection(
        slug=slug,
        internal_name=title,
        public_title=title,
        status="published",
        mode="manual",
        min_items=min_items,
        max_items=6,
        **kwargs,
    )


def _category_titles(root: ET.Element) -> list[str]:
    return [
        str(category.text)
        for category in root.findall("./shop/categories/category")
    ]


def _offers(root: ET.Element) -> list[ET.Element]:
    return root.findall("./shop/offers/offer")


@pytest.mark.asyncio
async def test_public_feed_is_unauthenticated_and_matches_manager_download(async_client, db):
    brand = Brand(title="Daichi", slug="daichi", is_published=True)
    product = _product(
        title="Daichi Alpha 12",
        slug="daichi-alpha-12",
        brand=brand,
        main_image="/media/products/daichi-alpha.jpg",
    )
    active_tariff = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж настенного кондиционера",
        estimate_template="Монтаж кондиционера",
        category="Wall",
        power_range="12",
        base_price=500,
        included_route_meters=3,
        is_active=True,
    )
    inactive_tariff = ServiceTariff(
        service_kind="repair",
        selector_label="Архивный ремонт",
        estimate_template="Архивный ремонт",
        category="repair",
        power_range="",
        base_price=999,
        is_active=False,
    )
    zero_tariff = ServiceTariff(
        service_kind="maintenance",
        selector_label="Бесплатное обслуживание",
        estimate_template="Не должно попасть в feed",
        category="maintenance",
        power_range="",
        base_price=0,
        is_active=True,
    )
    db.add_all([product, active_tariff, inactive_tariff, zero_tariff])
    await db.commit()

    public = await async_client.get("/api/v1/feeds/yandex-business.yml")
    assert public.status_code == 200
    assert public.headers["content-type"].startswith("application/xml")
    assert "content-disposition" not in public.headers
    public_root = ET.fromstring(public.content)
    assert public_root.tag == "yml_catalog"
    assert "Ремонт" not in _category_titles(public_root)
    assert "Обслуживание" not in _category_titles(public_root)
    assert "Архивный ремонт" not in public.text
    assert "Бесплатное обслуживание" not in public.text

    unauthenticated_manager = await async_client.get(
        "/api/manager/yandex-business/price-list.yml"
    )
    assert unauthenticated_manager.status_code == 401

    manager = await async_client.get(
        "/api/manager/yandex-business/price-list.yml",
        headers=await _auth_headers(async_client),
    )
    assert manager.status_code == 200
    assert manager.content == public.content
    assert manager.headers["content-disposition"].startswith("attachment;")


@pytest.mark.asyncio
async def test_feed_orders_collections_brands_unbranded_and_services_without_duplicates(
    async_client,
    db,
):
    tcl = Brand(title="TCL", slug="tcl", sort_order=10)
    haier = Brand(title="Haier", slug="haier", sort_order=20)
    overlap = _product(
        title="TCL First",
        slug="tcl-first",
        brand=tcl,
        main_image="/media/tcl-first.webp",
    )
    second_collection_item = _product(
        title="TCL Heat",
        slug="tcl-heat",
        brand=tcl,
        main_image=None,
        specs={},
    )
    tcl_remaining = _product(
        title="TCL Brand",
        slug="tcl-brand",
        brand=tcl,
        main_image="/media/tcl-brand.png",
    )
    haier_remaining = _product(
        title="Haier Brand",
        slug="haier-brand",
        brand=haier,
        main_image="/media/haier-brand.jpg",
    )
    unbranded = _product(title="Без бренда", slug="without-brand")
    first = _collection(slug="value", title="Цена-качество")
    second = _collection(slug="heat", title="Для обогрева")
    service = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж",
        estimate_template="Монтаж кондиционера",
        category="Wall",
        power_range="12",
        base_price=500,
        is_active=True,
    )
    db.add_all(
        [
            overlap,
            second_collection_item,
            tcl_remaining,
            haier_remaining,
            unbranded,
            first,
            second,
            service,
        ]
    )
    await db.flush()
    db.add_all(
        [
            ProductCollectionItem(
                collection_id=first.id,
                product_id=overlap.id,
                position=0,
            ),
            ProductCollectionItem(
                collection_id=second.id,
                product_id=overlap.id,
                position=0,
            ),
            ProductCollectionItem(
                collection_id=second.id,
                product_id=second_collection_item.id,
                position=1,
            ),
            ProductCollectionPlacement(
                surface_key="yandex_business",
                slot_key="categories",
                collection_id=first.id,
                position=10,
            ),
            ProductCollectionPlacement(
                surface_key="yandex_business",
                slot_key="categories",
                collection_id=second.id,
                position=20,
            ),
        ]
    )
    await db.commit()

    response = await async_client.get("/api/v1/feeds/yandex-business.yml")
    assert response.status_code == 200, response.text
    root = ET.fromstring(response.content)
    assert _category_titles(root) == [
        "Цена-качество",
        "Для обогрева",
        "TCL",
        "Haier",
        "Другие модели",
        "Монтаж",
    ]

    product_offers = [
        offer for offer in _offers(root) if int(offer.attrib["id"]) < 900_000_000
    ]
    offer_ids = [int(offer.attrib["id"]) for offer in product_offers]
    assert len(offer_ids) == len(set(offer_ids)) == 5
    assert offer_ids == [
        overlap.id,
        second_collection_item.id,
        tcl_remaining.id,
        haier_remaining.id,
        unbranded.id,
    ]
    overlap_offer = root.find(f"./shop/offers/offer[@id='{overlap.id}']")
    assert overlap_offer is not None
    assert overlap_offer.findtext("categoryId") == str(
        YandexBusinessPriceListService.COLLECTION_CATEGORY_OFFSET + first.id
    )
    assert root.find(f"./shop/offers/offer[@id='{second_collection_item.id}']/picture") is None
    assert ".webp" not in response.text.lower()

    category_ids = {
        category.attrib["id"]
        for category in root.findall("./shop/categories/category")
    }
    used_category_ids = {offer.findtext("categoryId") for offer in _offers(root)}
    assert used_category_ids <= category_ids
    assert all(
        any(
            offer.findtext("categoryId") == category.attrib["id"]
            for offer in _offers(root)
        )
        for category in root.findall("./shop/categories/category")
    )


@pytest.mark.asyncio
async def test_feed_omits_inactive_empty_collections_and_keeps_primary_title_for_fallback(
    async_client,
    db,
):
    now = datetime.now(timezone.utc)
    fallback_product = _product(
        title="Fallback product",
        slug="fallback-product",
    )
    fallback = _collection(slug="fallback", title="Резерв")
    primary = _collection(slug="primary", title="Основная")
    empty = _collection(slug="empty", title="Пустая", min_items=2)
    draft = _collection(slug="draft", title="Черновик")
    draft.status = "draft"
    archived = _collection(slug="archived", title="Архив")
    archived.status = "archived"
    future = _collection(
        slug="future",
        title="Будущая",
        starts_at=now + timedelta(days=1),
    )
    expired = _collection(
        slug="expired",
        title="Истёкшая",
        ends_at=now - timedelta(days=1),
    )
    disabled = _collection(slug="disabled", title="Выключенная")
    db.add_all(
        [
            fallback_product,
            fallback,
            primary,
            empty,
            draft,
            archived,
            future,
            expired,
            disabled,
        ]
    )
    await db.flush()
    primary.fallback_collection_id = fallback.id
    db.add(
        ProductCollectionItem(
            collection_id=fallback.id,
            product_id=fallback_product.id,
            position=0,
        )
    )
    for position, collection in enumerate(
        [primary, empty, draft, archived, future, expired, disabled]
    ):
        db.add(
            ProductCollectionPlacement(
                surface_key="yandex_business",
                slot_key="categories",
                collection_id=collection.id,
                position=position,
                is_enabled=collection is not disabled,
            )
        )
    await db.commit()

    response = await async_client.get("/api/v1/feeds/yandex-business.yml")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    titles = _category_titles(root)
    assert "Основная" in titles
    assert "Резерв" not in titles
    assert "Пустая" not in titles
    assert "Черновик" not in titles
    assert "Архив" not in titles
    assert "Будущая" not in titles
    assert "Истёкшая" not in titles
    assert "Выключенная" not in titles

    offer = root.find(f"./shop/offers/offer[@id='{fallback_product.id}']")
    assert offer is not None
    assert offer.findtext("categoryId") == str(
        YandexBusinessPriceListService.COLLECTION_CATEGORY_OFFSET + primary.id
    )


@pytest.mark.asyncio
async def test_feed_uses_automatic_and_hybrid_resolver_modes(async_client, db):
    brand = Brand(title="Resolver", slug="resolver")
    pinned = _product(title="Pinned", slug="pinned", brand=brand, price=3000)
    automatic = _product(title="Automatic", slug="automatic", brand=brand, price=900)
    second_automatic = _product(
        title="Second automatic",
        slug="second-automatic",
        brand=brand,
        price=1000,
    )
    hybrid = ProductCollection(
        slug="hybrid",
        internal_name="Hybrid",
        public_title="Hybrid",
        status="published",
        mode="hybrid",
        sort_mode="price_asc",
        rule_config={"brand_ids": []},
        min_items=2,
        max_items=2,
    )
    automatic_collection = ProductCollection(
        slug="automatic-collection",
        internal_name="Automatic",
        public_title="Automatic",
        status="published",
        mode="automatic",
        sort_mode="price_asc",
        rule_config={"min_price": 1000, "max_price": 1000},
        min_items=1,
        max_items=1,
    )
    db.add_all([pinned, automatic, second_automatic, hybrid, automatic_collection])
    await db.flush()
    hybrid.rule_config = {"brand_ids": [brand.id]}
    db.add(
        ProductCollectionItem(
            collection_id=hybrid.id,
            product_id=pinned.id,
            position=0,
            is_pinned=True,
        )
    )
    db.add_all(
        [
            ProductCollectionPlacement(
                surface_key="yandex_business",
                slot_key="categories",
                collection_id=hybrid.id,
                position=1,
            ),
            ProductCollectionPlacement(
                surface_key="yandex_business",
                slot_key="categories",
                collection_id=automatic_collection.id,
                position=2,
            ),
        ]
    )
    await db.commit()

    response = await async_client.get("/api/v1/feeds/yandex-business.yml")
    assert response.status_code == 200, response.text
    root = ET.fromstring(response.content)
    offers = [
        int(offer.attrib["id"])
        for offer in _offers(root)
        if int(offer.attrib["id"]) < 900_000_000
    ]
    assert offers[:2] == [pinned.id, automatic.id]
    assert offers.count(automatic.id) == 1
    assert offers[:3] == [pinned.id, automatic.id, second_automatic.id]
