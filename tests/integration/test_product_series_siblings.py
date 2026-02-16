import pytest

from models import Product, ProductTagLink, Tag, TagGroup


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

    main = Product(title="Main", slug="main", price=1000, area=25, is_published=True)
    sibling_same_brand = Product(title="Sibling A", slug="sibling-a", price=1400, area=30, is_published=True)
    sibling_other_brand = Product(title="Sibling B", slug="sibling-b", price=1200, area=30, is_published=True)
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
