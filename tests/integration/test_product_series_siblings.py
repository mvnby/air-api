import pytest

from models import Brand, Product, ProductSeries, ProductTagLink, Tag, TagGroup


@pytest.mark.asyncio
async def test_product_detail_contains_series_siblings(async_client, db):
    brand_group = TagGroup(title="Brand", slug="brand")
    series_group = TagGroup(title="Series", slug="series")
    db.add(brand_group)
    db.add(series_group)
    await db.commit()
    await db.refresh(brand_group)
    await db.refresh(series_group)

    brand_a = Tag(title="Brand A", slug="brand-a", group_id=brand_group.id)
    brand_b = Tag(title="Brand B", slug="brand-b", group_id=brand_group.id)
    series_x = Tag(title="Series X", slug="series-x", group_id=series_group.id)
    db.add(brand_a)
    db.add(brand_b)
    db.add(series_x)
    await db.commit()
    await db.refresh(brand_a)
    await db.refresh(brand_b)
    await db.refresh(series_x)

    main = Product(title="Main", slug="main", price=1000, specs={"area_m2": 25}, is_published=True)
    sibling_same_brand = Product(title="Sibling A", slug="sibling-a", price=1400, specs={"area_m2": 30}, is_published=True)
    sibling_other_brand = Product(title="Sibling B", slug="sibling-b", price=1200, specs={"area_m2": 30}, is_published=True)
    db.add(main)
    db.add(sibling_same_brand)
    db.add(sibling_other_brand)
    await db.commit()
    await db.refresh(main)
    await db.refresh(sibling_same_brand)
    await db.refresh(sibling_other_brand)

    db.add_all(
        [
            ProductTagLink(product_id=main.id, tag_id=brand_a.id),
            ProductTagLink(product_id=main.id, tag_id=series_x.id),
            ProductTagLink(product_id=sibling_same_brand.id, tag_id=brand_a.id),
            ProductTagLink(product_id=sibling_same_brand.id, tag_id=series_x.id),
            ProductTagLink(product_id=sibling_other_brand.id, tag_id=brand_b.id),
            ProductTagLink(product_id=sibling_other_brand.id, tag_id=series_x.id),
        ]
    )
    await db.commit()

    response = await async_client.get("/api/v1/products/main")
    assert response.status_code == 200
    data = response.json()

    siblings = data["series_siblings"]
    assert len(siblings) == 2
    assert siblings[0]["slug"] == "sibling-a"
    assert siblings[1]["slug"] == "sibling-b"


@pytest.mark.asyncio
async def test_product_detail_contains_series_and_series_id_siblings(async_client, db):
    brand = Brand(title="TCL", slug="tcl", is_published=True)
    db.add(brand)
    await db.flush()

    series = ProductSeries(
        title="FreshIN",
        slug="freshin",
        brand_id=brand.id,
        description="Fresh air product line",
        hero_image="/media/series/freshin.webp",
        features=["Fresh air intake", "Self-cleaning"],
        is_published=True,
    )
    db.add(series)
    await db.flush()

    main = Product(
        title="TCL FreshIN 35",
        slug="tcl-freshin-35",
        price=1900,
        specs={"area_m2": 35},
        power_cooling=3.5,
        brand_id=brand.id,
        series_id=series.id,
        is_published=True,
    )
    sibling_25 = Product(
        title="TCL FreshIN 25",
        slug="tcl-freshin-25",
        price=1500,
        specs={"area_m2": 25},
        power_cooling=2.6,
        brand_id=brand.id,
        series_id=series.id,
        is_published=True,
    )
    sibling_50 = Product(
        title="TCL FreshIN 50",
        slug="tcl-freshin-50",
        price=2600,
        specs={"area_m2": 50},
        power_cooling=5.2,
        brand_id=brand.id,
        series_id=series.id,
        is_published=True,
    )
    other_series = Product(
        title="TCL Elite 25",
        slug="tcl-elite-25",
        price=1300,
        specs={"area_m2": 25},
        brand_id=brand.id,
        is_published=True,
    )
    db.add_all([main, sibling_50, sibling_25, other_series])
    await db.commit()
    await db.refresh(main)

    response = await async_client.get(f"/api/v1/products/{main.slug}")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["series"] == {
        "id": series.id,
        "title": "FreshIN",
        "slug": "freshin",
        "tagline": None,
        "short_description": None,
        "description": "Fresh air product line",
        "hero_image": "/media/series/freshin.webp",
        "gallery_images": [],
        "features": ["Fresh air intake", "Self-cleaning"],
        "brand_features": [],
        "feature_blocks": [],
        "content_blocks": [],
        "footnotes": [],
        "seo_title": None,
        "seo_description": None,
        "source_url": None,
    }

    sibling_slugs = [item["slug"] for item in data["series_siblings"]]
    assert sibling_slugs[:2] == ["tcl-freshin-25", "tcl-freshin-50"]
    assert "tcl-elite-25" not in sibling_slugs
