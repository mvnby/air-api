import xml.etree.ElementTree as ET

import pytest

from models import Brand, Product, ServiceTariff, Tag, TagGroup
from services.yandex_business_price_list_service import YandexBusinessPriceListService


@pytest.mark.asyncio
async def test_yandex_business_price_list_builds_catalog(monkeypatch):
    brand = Brand(id=1, title="Daichi", slug="daichi")
    category_group = TagGroup(id=1, title="Категория", slug="category")
    category_tag = Tag(
        id=7,
        title="Бытовые кондиционеры",
        slug="cat-household",
        group=category_group,
    )
    product = Product(
        id=11,
        title="Daichi Alpha 12",
        slug="daichi-alpha-12",
        description="Инверторный кондиционер",
        price=1299,
        main_image="media/products/daichi-alpha.jpg",
        brand=brand,
        tags=[category_tag],
    )
    tariff = ServiceTariff(
        id=3,
        service_kind="maintenance",
        selector_label="Обслуживание кондиционера",
        estimate_template="Чистка внутреннего и наружного блока",
        category="maintenance",
        power_range="до 3.5 кВт",
        base_price=120,
        included_route_meters=0,
        is_active=True,
    )

    async def load_products(_session):
        return [product]

    async def load_tariffs(_session):
        return [tariff]

    monkeypatch.setattr(YandexBusinessPriceListService, "_load_products", load_products)
    monkeypatch.setattr(YandexBusinessPriceListService, "_load_tariffs", load_tariffs)

    xml_bytes = await YandexBusinessPriceListService.build_xml(
        session=None,
        site_base_url="https://example.mvn.by/",
    )

    root = ET.fromstring(xml_bytes)
    categories = {
        int(category.attrib["id"]): category.text
        for category in root.findall("./shop/categories/category")
    }
    assert categories[100007] == "Бытовые кондиционеры"
    assert categories[203] == "Обслуживание"

    product_offer = root.find("./shop/offers/offer[@id='11']")
    assert product_offer is not None
    assert product_offer.findtext("vendor") == "Daichi"
    assert product_offer.findtext("currencyId") == "BYN"
    assert product_offer.findtext("picture") == "https://example.mvn.by/media/products/daichi-alpha.jpg"
    assert product_offer.findtext("url") == "https://example.mvn.by/product/daichi-alpha-12"

    service_offer = root.find("./shop/offers/offer[@id='900000003']")
    assert service_offer is not None
    assert service_offer.findtext("name") == "Обслуживание кондиционера, мощностью до 3,5 кВт"
    assert service_offer.findtext("price") == "120"
    assert service_offer.findtext("currencyId") == "BYN"
    assert service_offer.findtext("url") == "https://example.mvn.by/obslujivanie-kondicionerov"
