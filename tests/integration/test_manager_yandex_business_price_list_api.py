import xml.etree.ElementTree as ET

import pytest

from core.config import settings
from models import Brand, Product, ServiceTariff, Tag, TagGroup


async def _auth_headers(async_client):
    login_resp = await async_client.post(
        "/login/access-token",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_manager_yandex_business_price_list_exports_products_and_tariffs(async_client, db):
    brand = Brand(title="Daichi", slug="daichi", is_published=True)
    category_group = TagGroup(title="Категория", slug="category", is_public=True)
    category_tag = Tag(
        title="Бытовые кондиционеры",
        slug="cat-household",
        group=category_group,
        is_public=True,
    )
    product = Product(
        title="Daichi Alpha 12",
        slug="daichi-alpha-12",
        description="Инверторный кондиционер для квартиры",
        price=1299,
        specs={"area_m2": 35},
        main_image="/media/products/daichi-alpha.jpg",
        is_published=True,
        brand=brand,
        tags=[category_tag],
    )
    hidden_product = Product(
        title="Скрытый товар",
        slug="hidden-product",
        description="Не должен попасть в прайс",
        price=1,
        is_published=False,
    )
    active_tariff = ServiceTariff(
        service_kind="installation",
        selector_label="Монтаж настенного кондиционера",
        estimate_template="Монтаж кондиционера, включая расходные материалы",
        category="Wall",
        power_range="12",
        base_price=500,
        included_route_meters=3,
        is_active=True,
        sort_order=1,
    )
    pre_install_tariff = ServiceTariff(
        service_kind="pre_install",
        selector_label="Закладка коммуникаций под кондиционер",
        estimate_template="Закладка межблочной трассы под кондиционер, включая материалы до 3 м",
        category="Wall",
        power_range="07-12",
        base_price=500,
        included_route_meters=3,
        is_active=True,
        sort_order=2,
    )
    inactive_tariff = ServiceTariff(
        service_kind="repair",
        selector_label="Архивный ремонт",
        estimate_template="Архивный ремонт",
        category="repair",
        power_range="",
        base_price=999,
        included_route_meters=0,
        is_active=False,
        sort_order=1,
    )
    db.add(product)
    db.add(hidden_product)
    db.add(active_tariff)
    db.add(pre_install_tariff)
    db.add(inactive_tariff)
    await db.commit()
    await db.refresh(product)
    await db.refresh(active_tariff)
    await db.refresh(pre_install_tariff)

    headers = await _auth_headers(async_client)
    response = await async_client.get(
        "/api/manager/yandex-business/price-list.yml?site_base_url=https://example.mvn.by",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(response.content)
    assert root.tag == "yml_catalog"

    offers = root.findall("./shop/offers/offer")
    offer_names = [offer.findtext("name") for offer in offers]
    assert "Daichi Alpha 12" in offer_names
    assert "Скрытый товар" not in offer_names
    assert any(
        name and name.startswith("Монтаж настенного кондиционера")
        for name in offer_names
    )
    assert any(
        name and name.startswith("Закладка коммуникаций под кондиционер")
        for name in offer_names
    )
    assert "Архивный ремонт" not in offer_names

    product_offer = next(offer for offer in offers if offer.findtext("name") == "Daichi Alpha 12")
    assert product_offer.findtext("vendor") == "Daichi"
    assert product_offer.findtext("price") == "1299"
    assert product_offer.findtext("currencyId") == "BYN"
    assert product_offer.findtext("picture") == "https://example.mvn.by/media/products/daichi-alpha.jpg"
    assert product_offer.findtext("url") == "https://example.mvn.by/product/daichi-alpha-12"

    service_offer = next(
        offer
        for offer in offers
        if (offer.findtext("name") or "").startswith("Монтаж настенного")
    )
    assert service_offer.findtext("price") == "500"
    assert service_offer.findtext("url") == "https://example.mvn.by/montaj-konditionerov"

    pre_install_offer = next(
        offer
        for offer in offers
        if (offer.findtext("name") or "").startswith("Закладка коммуникаций")
    )
    assert pre_install_offer.findtext("price") == "500"
    assert pre_install_offer.findtext("url") == (
        "https://example.mvn.by/services/zakladka-kommunikaciy-kondicionera"
    )
