import xml.etree.ElementTree as ET

import pytest

from core.config import settings
from models import (
    Brand,
    Product,
    ProductImage,
    ProductImageVariant,
    ServiceTariff,
)
from services.yandex_business_feed_text import sanitize_yandex_description
from services.yandex_business_price_list_service import (
    ProductOffer,
    YandexBusinessPriceListService,
    YandexCategory,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "<style>.ferrum-clean * { margin: 0 }</style>"
            "<p>Инверторный кондиционер</p>",
            "Инверторный кондиционер",
        ),
        (
            "<script>alert(1)</script><div>Тихая работа</div>",
            "Тихая работа",
        ),
        ("<p>Тихий&nbsp;&amp;&nbsp;надёжный</p>", "Тихий & надёжный"),
        (
            ".ferrum-clean * { margin: 0; padding: 0 } <p>Чистый воздух</p>",
            "Чистый воздух",
        ),
        ("Обычный plain text", "Обычный plain text"),
        ("<style>body { color: red }</style><script>x()</script>", "Fallback"),
    ],
)
def test_description_sanitizer(source, expected):
    assert sanitize_yandex_description(source, fallback="Fallback", limit=3000) == expected


def test_description_is_truncated_after_html_cleanup():
    source = "<style>" + ("x" * 100) + "</style><p>123456789</p>"
    assert sanitize_yandex_description(source, fallback="Fallback", limit=7) == "123456…"


@pytest.mark.parametrize(
    ("image_url", "expected"),
    [
        ("/media/product.jpg", "https://mvn.by/media/product.jpg"),
        ("/media/product.JPEG?rev=1", "https://mvn.by/media/product.JPEG?rev=1"),
        ("/media/product.png", "https://mvn.by/media/product.png"),
        ("/media/product.webp", None),
        (None, None),
    ],
)
def test_product_picture_accepts_only_yandex_compatible_formats(image_url, expected):
    product = Product(
        id=1,
        title="Split",
        slug="split",
        price=100,
        main_image=image_url,
    )
    assert YandexBusinessPriceListService._product_picture(product, "https://mvn.by") == expected


def test_product_picture_uses_real_ready_jpeg_variant_instead_of_webp():
    image = ProductImage(
        id=10,
        product_id=1,
        url="/media/product.webp",
        variants=[
            ProductImageVariant(
                id=20,
                product_image_id=10,
                variant_type="original",
                url="/media/product-source.jpg",
                processing_status="ready",
            )
        ],
    )
    product = Product(
        id=1,
        title="Split",
        slug="split",
        price=100,
        main_image="/media/product.webp",
        gallery_images=[image],
    )
    assert YandexBusinessPriceListService._product_picture(
        product,
        "https://mvn.by",
    ) == "https://mvn.by/media/product-source.jpg"


@pytest.mark.asyncio
async def test_yandex_business_price_list_builds_catalog(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://example.mvn.by/")
    brand = Brand(id=1, title="Daichi", slug="daichi")
    product = Product(
        id=11,
        title="Daichi Alpha 12",
        slug="daichi-alpha-12",
        description=(
            "<style>.x { color:red }</style><p>Инверторный кондиционер</p>"
        ),
        price=1299,
        main_image="media/products/daichi-alpha.jpg",
        brand=brand,
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
    brand_category = YandexCategory(id=2_000_001, title="Daichi")

    async def load_products(_session):
        return [product]

    async def load_tariffs(_session):
        return [tariff]

    async def build_product_catalog(_session, _products):
        return [brand_category], [ProductOffer(product=product, category=brand_category)]

    monkeypatch.setattr(YandexBusinessPriceListService, "_load_products", load_products)
    monkeypatch.setattr(YandexBusinessPriceListService, "_load_tariffs", load_tariffs)
    monkeypatch.setattr(
        YandexBusinessPriceListService,
        "_build_product_catalog",
        build_product_catalog,
    )

    first = await YandexBusinessPriceListService.build_xml(session=None)
    second = await YandexBusinessPriceListService.build_xml(session=None)
    assert first == second

    root = ET.fromstring(first)
    category_titles = [
        category.text for category in root.findall("./shop/categories/category")
    ]
    assert category_titles == ["Daichi", "Обслуживание"]

    product_offer = root.find("./shop/offers/offer[@id='11']")
    assert product_offer is not None
    assert product_offer.findtext("vendor") == "Daichi"
    assert product_offer.findtext("picture") == (
        "https://example.mvn.by/media/products/daichi-alpha.jpg"
    )
    assert product_offer.findtext("description") == "Инверторный кондиционер"
    assert product_offer.findtext("url") == (
        "https://example.mvn.by/product/daichi-alpha-12"
    )
    assert ".webp" not in first.decode()


def test_category_id_ranges_do_not_overlap():
    ids = {
        YandexBusinessPriceListService.COLLECTION_CATEGORY_OFFSET + 1,
        YandexBusinessPriceListService.BRAND_CATEGORY_OFFSET + 1,
        YandexBusinessPriceListService.UNBRANDED_CATEGORY.id,
        *(
            category.id
            for category in YandexBusinessPriceListService.SERVICE_KIND_CATEGORIES.values()
        ),
    }
    assert len(ids) == 8


def test_category_source_ids_cannot_cross_reserved_ranges():
    with pytest.raises(ValueError, match="out of range"):
        YandexBusinessPriceListService._scoped_category_id(
            YandexBusinessPriceListService.COLLECTION_CATEGORY_OFFSET,
            YandexBusinessPriceListService.CATEGORY_RANGE_SIZE,
        )
