import pytest
from httpx import AsyncClient

from models import Brand, Feature, FeatureCategory, FeatureSeriesLink, Product, ProductSeries


@pytest.mark.asyncio
async def test_public_series_page_uses_public_product_contract(
    async_client: AsyncClient,
    db,
):
    brand = Brand(
        title="TCL",
        slug="tcl",
        logo_url="/media/brands/tcl.svg",
        is_published=True,
    )
    db.add(brand)
    await db.flush()

    series = ProductSeries(
        brand_id=brand.id,
        title="FreshIN 3.0",
        slug="freshin-3",
        tagline="Приток свежего воздуха",
        short_description="Флагманская серия TCL.",
        description="Полное описание серии.",
        hero_image="/media/series/freshin.webp",
        gallery_images=["/media/series/freshin-1.webp"],
        features=["FreshIN+"],
        feature_blocks=[{"title": "FreshIN+", "text": "Приток воздуха"}],
        content_blocks=[{"kind": "text", "title": "Комфорт", "text": "Описание"}],
        footnotes=["Характеристики зависят от модели."],
        seo_title="TCL FreshIN 3.0",
        seo_description="Серия TCL FreshIN 3.0.",
        source_url="https://example.com/tcl.pdf",
        is_published=True,
    )
    related_empty = ProductSeries(
        brand_id=brand.id,
        title="BreezeIN",
        slug="breezein",
        short_description="Комфортная подача воздуха.",
        hero_image="/media/series/breezein.webp",
        is_published=True,
        sort_order=10,
    )
    related_with_product = ProductSeries(
        brand_id=brand.id,
        title="Elite",
        slug="elite",
        is_published=True,
        sort_order=20,
    )
    hidden_series = ProductSeries(
        brand_id=brand.id,
        title="Hidden",
        slug="hidden",
        is_published=False,
    )
    db.add_all([series, related_empty, related_with_product, hidden_series])
    await db.flush()

    category = FeatureCategory(slug="air", name="Воздух")
    db.add(category)
    await db.flush()
    feature = Feature(
        brand_id=brand.id,
        category_id=category.id,
        scope_type="series",
        name="FreshIN+",
        slug="freshin-plus",
        full_description="Приток наружного воздуха.",
        is_active=True,
    )
    db.add(feature)
    await db.flush()
    db.add(
        FeatureSeriesLink(
            series_id=series.id,
            feature_id=feature.id,
            is_enabled=True,
            sort_order=10,
        )
    )

    published = Product(
        title="TCL FreshIN TAC-09CHSD/FCI",
        slug="tcl-freshin-09",
        price=3200,
        specs={"area_m2": 25, "__filter_min_heat": -20},
        brand_id=brand.id,
        series_id=series.id,
        is_published=True,
    )
    hidden = Product(
        title="TCL FreshIN hidden",
        slug="tcl-freshin-hidden",
        price=3300,
        brand_id=brand.id,
        series_id=series.id,
        is_published=False,
    )
    related_product = Product(
        title="TCL Elite",
        slug="tcl-elite",
        price=1800,
        brand_id=brand.id,
        series_id=related_with_product.id,
        is_published=True,
    )
    hidden_related_product = Product(
        title="TCL Elite hidden",
        slug="tcl-elite-hidden",
        price=1700,
        brand_id=brand.id,
        series_id=related_with_product.id,
        is_published=False,
    )
    db.add_all([published, hidden, related_product, hidden_related_product])
    await db.commit()

    response = await async_client.get(
        "/api/v1/content/brands/tcl/series/freshin-3"
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["brand"] == {
        "id": brand.id,
        "title": "TCL",
        "slug": "tcl",
        "logo_url": "/media/brands/tcl.svg",
    }
    assert payload["series"]["slug"] == "freshin-3"
    assert payload["series"]["brand_features"][0]["slug"] == "freshin-plus"
    assert [item["slug"] for item in payload["products"]] == ["tcl-freshin-09"]
    assert "__filter_min_heat" not in payload["products"][0]["specs"]
    assert payload["related_series"] == [
        {
            "title": "BreezeIN",
            "slug": "breezein",
            "short_description": "Комфортная подача воздуха.",
            "hero_image": "/media/series/breezein.webp",
            "products_count": 0,
        },
        {
            "title": "Elite",
            "slug": "elite",
            "short_description": None,
            "hero_image": None,
            "products_count": 1,
        },
    ]

    catalog_response = await async_client.get(
        "/api/v1/products",
        params={"q": "TCL FreshIN TAC-09CHSD/FCI", "limit": 5},
    )
    assert catalog_response.status_code == 200, catalog_response.text
    assert payload["products"][0] == catalog_response.json()["items"][0]


@pytest.mark.asyncio
async def test_public_series_page_allows_empty_series_and_hides_unpublished_data(
    async_client: AsyncClient,
    db,
):
    brand = Brand(title="TCL", slug="tcl", is_published=True)
    hidden_brand = Brand(title="Hidden", slug="hidden", is_published=False)
    db.add_all([brand, hidden_brand])
    await db.flush()

    empty_series = ProductSeries(
        brand_id=brand.id,
        title="Empty",
        slug="empty",
        is_published=True,
    )
    hidden_series = ProductSeries(
        brand_id=brand.id,
        title="Draft",
        slug="draft",
        is_published=False,
    )
    hidden_brand_series = ProductSeries(
        brand_id=hidden_brand.id,
        title="Visible series",
        slug="visible-series",
        is_published=True,
    )
    db.add_all([empty_series, hidden_series, hidden_brand_series])
    await db.commit()

    response = await async_client.get("/api/v1/content/brands/tcl/series/empty")
    assert response.status_code == 200, response.text
    assert response.json()["products"] == []

    for path in (
        "/api/v1/content/brands/tcl/series/draft",
        "/api/v1/content/brands/hidden/series/visible-series",
        "/api/v1/content/brands/tcl/series/missing",
        "/api/v1/content/brands/missing/series/empty",
    ):
        missing_response = await async_client.get(path)
        assert missing_response.status_code == 404
