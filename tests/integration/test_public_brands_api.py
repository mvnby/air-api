import pytest
from httpx import AsyncClient

from models import Brand, Feature, FeatureBrandLink, FeatureCategory, Product, ProductSeries


@pytest.mark.asyncio
async def test_public_brands_include_only_published_brands_with_published_products(
    async_client: AsyncClient,
    db,
):
    tcl = Brand(
        title="TCL",
        slug="tcl",
        logo_url="/media/brands/tcl.svg",
        short_description="Технологичные серии для разных сценариев комфорта.",
        description="Кондиционеры TCL для квартир и офисов.",
        is_published=True,
        sort_order=20,
    )
    mdv = Brand(title="MDV", slug="mdv", is_published=True, sort_order=10)
    hidden = Brand(title="Hidden", slug="hidden", is_published=False, sort_order=0)
    empty = Brand(title="Empty", slug="empty", is_published=True, sort_order=30)
    db.add_all([tcl, mdv, hidden, empty])
    await db.flush()
    featured_series = [
        ProductSeries(
            brand_id=tcl.id,
            title=f"Featured {index}",
            slug=f"featured-{index}",
            is_featured=True,
            is_published=True,
            sort_order=sort_order,
        )
        for index, sort_order in enumerate((40, 10, 20, 30), start=1)
    ]
    draft_featured_series = ProductSeries(
        brand_id=tcl.id,
        title="Draft featured",
        slug="draft-featured",
        is_featured=True,
        is_published=False,
        sort_order=5,
    )
    other_brand_featured_series = ProductSeries(
        brand_id=hidden.id,
        title="Other brand featured",
        slug="other-brand-featured",
        is_featured=True,
        is_published=True,
        sort_order=1,
    )
    ordinary_series = ProductSeries(
        brand_id=tcl.id,
        title="Ordinary",
        slug="ordinary",
        is_featured=False,
        is_published=True,
        sort_order=0,
    )
    db.add_all(
        [
            *featured_series,
            draft_featured_series,
            other_brand_featured_series,
            ordinary_series,
        ]
    )
    category = FeatureCategory(slug="comfort", name="Комфорт", sort_order=10)
    db.add(category)
    await db.flush()
    active_feature = Feature(
                brand_id=tcl.id,
                category_id=category.id,
                scope_type="brand",
                name="Fresh Air",
                slug="fresh-air",
                full_description="Фильтрация воздуха в бытовых сериях.",
                image_url="/media/brands/tcl/fresh-air.webp",
                icon="air",
                footnote="Доступно не во всех моделях",
                aliases=["filter"],
                is_active=True,
                sort_order=20,
            )
    draft_feature = Feature(
                brand_id=tcl.id,
                category_id=category.id,
                scope_type="brand",
                name="Draft feature",
                slug="draft-feature",
                is_active=False,
                sort_order=10,
            )
    db.add_all([active_feature, draft_feature])
    await db.flush()
    db.add_all([
        FeatureBrandLink(brand_id=tcl.id, feature_id=active_feature.id, sort_order=20),
        FeatureBrandLink(brand_id=tcl.id, feature_id=draft_feature.id, sort_order=10),
        FeatureBrandLink(brand_id=mdv.id, feature_id=active_feature.id, sort_order=5),
    ])

    db.add_all(
        [
            Product(
                title="TCL published",
                slug="tcl-published",
                price=1000,
                specs={"area_m2": 25},
                brand_id=tcl.id,
                is_published=True,
            ),
            Product(
                title="TCL draft",
                slug="tcl-draft",
                price=1000,
                specs={"area_m2": 25},
                brand_id=tcl.id,
                is_published=False,
            ),
            Product(
                title="MDV published",
                slug="mdv-published",
                price=1000,
                specs={"area_m2": 25},
                brand_id=mdv.id,
                is_published=True,
            ),
            Product(
                title="Hidden published",
                slug="hidden-published",
                price=1000,
                specs={"area_m2": 25},
                brand_id=hidden.id,
                is_published=True,
            ),
        ]
    )
    await db.commit()

    response = await async_client.get("/api/v1/content/brands")
    assert response.status_code == 200, response.text
    items = response.json()
    assert [item["slug"] for item in items] == ["mdv", "tcl"]

    tcl_payload = next(item for item in items if item["slug"] == "tcl")
    assert tcl_payload == {
        "id": tcl.id,
        "title": "TCL",
        "slug": "tcl",
        "logo_url": "/media/brands/tcl.svg",
        "short_description": "Технологичные серии для разных сценариев комфорта.",
        "description": "Кондиционеры TCL для квартир и офисов.",
        "products_count": 1,
        "sort_order": 20,
        "featured_series": [
            {"name": "Featured 2", "slug": "featured-2", "sort_order": 10},
            {"name": "Featured 3", "slug": "featured-3", "sort_order": 20},
            {"name": "Featured 4", "slug": "featured-4", "sort_order": 30},
            {"name": "Featured 1", "slug": "featured-1", "sort_order": 40},
        ],
    }

    detail_response = await async_client.get("/api/v1/content/brands/tcl")
    assert detail_response.status_code == 200, detail_response.text
    detail_payload = detail_response.json()
    assert detail_payload["products_count"] == 1
    assert detail_payload["featured_series"] == tcl_payload["featured_series"]
    assert detail_payload["features"] == [
        {
            "id": detail_payload["features"][0]["id"],
            "title": "Fresh Air",
            "slug": "fresh-air",
            "text": "Фильтрация воздуха в бытовых сериях.",
            "image_url": "/media/brands/tcl/fresh-air.webp",
            "icon": "air",
            "footnote": "Доступно не во всех моделях",
            "source_url": None,
            "aliases": ["filter"],
            "is_published": True,
            "sort_order": 20,
        }
    ]

    mdv_detail_response = await async_client.get("/api/v1/content/brands/mdv")
    assert mdv_detail_response.status_code == 200, mdv_detail_response.text
    mdv_detail_payload = mdv_detail_response.json()
    assert mdv_detail_payload["short_description"] is None
    assert mdv_detail_payload["featured_series"] == []
    assert mdv_detail_payload["features"] == []

    featured_series[1].is_published = False
    db.add(featured_series[1])
    await db.commit()
    transitioned_response = await async_client.get("/api/v1/content/brands/tcl")
    assert transitioned_response.status_code == 200, transitioned_response.text
    assert [
        item["slug"] for item in transitioned_response.json()["featured_series"]
    ] == ["featured-3", "featured-4", "featured-1"]

    for slug in ("hidden", "empty", "missing"):
        missing_response = await async_client.get(f"/api/v1/content/brands/{slug}")
        assert missing_response.status_code == 404
