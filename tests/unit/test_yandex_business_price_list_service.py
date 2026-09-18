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
from models.tenancy import TenantScope
from services.yandex_business_feed_text import sanitize_yandex_description
from services.yandex_business_price_list_service import (
    ProductCatalogBuild,
    ProductOffer,
    YandexBusinessPriceListService,
    YandexCategory,
)
from services.tenant_scope_service import SystemTenantScopeResolver
from services.yandex_business_feed_settings_service import (
    YandexBusinessFeedConfiguration,
    YandexBusinessFeedSettingsService,
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
    "image_url",
    [
        "/media/product.jpg",
        "/media/product.JPEG?rev=1",
        "/media/product.png",
        "/media/product.webp",
        None,
    ],
)
def test_product_picture_never_uses_original_image_directly(image_url):
    product = Product(
        id=1,
        title="Split",
        slug="split",
        price=100,
        main_image=image_url,
    )
    assert YandexBusinessPriceListService._product_picture(product, "https://mvn.by") is None


def test_product_picture_uses_ready_yandex_feed_variant():
    image = ProductImage(
        id=10,
        product_id=1,
        url="/media/product.webp",
        variants=[
            ProductImageVariant(
                id=20,
                product_image_id=10,
                variant_type="yandex_feed",
                url="/media/products/variants/yandex_feed/product-source.jpg",
                processing_status="ready",
                width=800,
                height=800,
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
    ) == "https://mvn.by/media/products/variants/yandex_feed/product-source.jpg"


@pytest.mark.asyncio
async def test_ready_image_requirement_excludes_only_products_without_variant():
    ready = Product(
        id=1,
        title="Ready",
        slug="ready",
        price=100,
        main_image="/media/ready.webp",
    )
    ready.gallery_images = [
        ProductImage(
            id=1,
            product_id=1,
            url="/media/ready.webp",
            variants=[
                ProductImageVariant(
                    id=1,
                    product_image_id=1,
                    variant_type="yandex_feed",
                    processing_status="ready",
                    url="/media/ready.jpg",
                    width=800,
                    height=800,
                )
            ],
        )
    ]
    missing = Product(id=2, title="Missing", slug="missing", price=100)

    eligible, excluded = await YandexBusinessPriceListService._eligible_products(
        session=None,
        products=[ready, missing],
        configuration=YandexBusinessFeedConfiguration(require_ready_image=True),
        base_url="https://mvn.by",
    )

    assert [product.id for product in eligible] == [1]
    assert [(item.product_id, item.reason) for item in excluded] == [
        (2, "missing_ready_yandex_image")
    ]


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
        main_image="media/products/daichi-alpha.webp",
        brand=brand,
    )
    product.gallery_images = [
        ProductImage(
            id=10,
            product_id=product.id,
            url=product.main_image,
            variants=[
                ProductImageVariant(
                    id=20,
                    product_image_id=10,
                    variant_type="yandex_feed",
                    url=(
                        "https://cdn.example.test/products/variants/"
                        "yandex_feed/daichi-alpha.jpg"
                    ),
                    processing_status="ready",
                    width=800,
                    height=800,
                )
            ],
        )
    ]
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

    tenant_scope = TenantScope(
        tenant_id=1,
        storefront_id=1,
        is_system=True,
    )

    async def resolve_scope(_session):
        return tenant_scope

    async def build_product_catalog(
        _session,
        _products,
        *,
        tenant_scope: TenantScope,
        configuration,
        base_url: str,
    ):
        assert tenant_scope.is_system
        assert configuration.selection_mode == "all_published"
        assert base_url == "https://example.mvn.by"
        return ProductCatalogBuild(
            categories=[brand_category],
            offers=[ProductOffer(product=product, category=brand_category)],
            collection_conflicts=[],
            excluded_products=[],
        )

    monkeypatch.setattr(YandexBusinessPriceListService, "_load_products", load_products)
    monkeypatch.setattr(YandexBusinessPriceListService, "_load_tariffs", load_tariffs)
    monkeypatch.setattr(SystemTenantScopeResolver, "resolve", resolve_scope)
    monkeypatch.setattr(
        YandexBusinessFeedSettingsService,
        "get",
        lambda *_args, **_kwargs: _default_yandex_feed_configuration(),
    )
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
        "https://cdn.example.test/products/variants/yandex_feed/daichi-alpha.jpg"
    )
    assert product_offer.findtext("description") == "Инверторный кондиционер"
    assert product_offer.findtext("url") == (
        "https://example.mvn.by/product/daichi-alpha-12"
    )
    assert ".webp" not in first.decode()

    report = await YandexBusinessPriceListService.build_quality_report(session=None)
    assert report.product_offer_count == 1
    assert report.product_picture_count == 1
    assert report.products_without_picture == []


@pytest.mark.asyncio
async def test_current_product_offer_ids_uses_configured_product_catalog(monkeypatch):
    product = Product(id=11, title="Daichi", slug="daichi", price=100)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
    configuration = await _default_yandex_feed_configuration()

    async def load_products(_session):
        return [product]

    async def resolve_scope(_session):
        return scope

    async def get_configuration(*_args, **_kwargs):
        return configuration_to_use

    async def build_product_catalog(
        _session,
        products,
        *,
        tenant_scope,
        configuration: YandexBusinessFeedConfiguration,
        base_url: str,
    ):
        assert products == [product]
        assert tenant_scope == scope
        assert configuration is configuration_to_use
        assert base_url
        return ProductCatalogBuild(
            categories=[],
            offers=[ProductOffer(product=product, category=YandexBusinessPriceListService.UNBRANDED_CATEGORY)],
            collection_conflicts=[],
            excluded_products=[],
        )

    configuration_to_use = configuration
    monkeypatch.setattr(YandexBusinessPriceListService, "_load_products", load_products)
    monkeypatch.setattr(SystemTenantScopeResolver, "resolve", resolve_scope)
    monkeypatch.setattr(
        YandexBusinessFeedSettingsService,
        "get",
        get_configuration,
    )
    monkeypatch.setattr(
        YandexBusinessPriceListService,
        "_build_product_catalog",
        build_product_catalog,
    )

    assert await YandexBusinessPriceListService.current_product_offer_ids(session=None) == {11}


async def _default_yandex_feed_configuration():
    from services.yandex_business_feed_settings_service import (
        YandexBusinessFeedConfiguration,
    )

    return YandexBusinessFeedConfiguration()


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


@pytest.mark.asyncio
async def test_empty_curated_collections_exclude_products_without_fallback(monkeypatch):
    from unittest.mock import AsyncMock
    from crud.product_collection import ProductCollectionDAO

    monkeypatch.setattr(ProductCollectionDAO, "list_placements", AsyncMock(return_value=[]))
    products = [Product(id=1, title="Specific model", slug="specific", price=100)]
    catalog = await YandexBusinessPriceListService._build_product_catalog(
        None,
        products,
        tenant_scope=TenantScope(tenant_id=1, storefront_id=1),
        configuration=YandexBusinessFeedConfiguration(selection_mode="curated_collections"),
        base_url="https://mvn.by",
    )
    assert catalog.offers == []
    assert [(item.product_id, item.reason) for item in catalog.excluded_products] == [
        (1, "not_in_curated_collections"),
    ]
