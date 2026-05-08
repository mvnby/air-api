import pytest

from models import Brand, Product, Tag, TagGroup


@pytest.mark.asyncio
async def test_filters_config_returns_ranges_and_allowed_tags(async_client, db):
    brand_group = TagGroup(title="Brand", slug="brand")
    expert_group = TagGroup(title="Expert", slug="expert-badge", is_expert_badge=True)
    technical_group = TagGroup(title="Tech", slug="wifi", is_public=False)
    db.add(brand_group)
    db.add(expert_group)
    db.add(technical_group)
    await db.commit()
    await db.refresh(brand_group)
    await db.refresh(expert_group)
    await db.refresh(technical_group)

    brand = Brand(
        title="Haier",
        slug="haier",
        logo_url="/uploads/brands/haier.svg",
        is_published=True,
        sort_order=10,
    )
    priority_brand = Brand(title="MDV", slug="mdv", is_published=True, sort_order=0)
    expert = Tag(title="Хит", slug="hit", group_id=expert_group.id, is_public=True)
    technical = Tag(title="Wi-Fi", slug="wifi-builtin", group_id=technical_group.id, is_public=True)
    db.add(brand)
    db.add(priority_brand)
    db.add(expert)
    db.add(technical)

    await db.flush()

    p1 = Product(title="A", slug="a", price=1000, area=20, brand_id=brand.id, is_published=True)
    p2 = Product(title="B", slug="b", price=2400, area=55, is_published=True)
    p3 = Product(title="C", slug="c", price=1600, area=35, brand_id=priority_brand.id, is_published=True)
    db.add(p1)
    db.add(p2)
    db.add(p3)
    await db.commit()

    response = await async_client.get("/api/v1/filters/config")
    assert response.status_code == 200
    data = response.json()

    assert data["price"] == {"min": 1000, "max": 2400}
    assert data["area"] == {"min": 20, "max": 55}
    assert [item["slug"] for item in data["brands"]] == ["mdv", "haier"]
    assert data["brands"][1]["logo_url"] == "/uploads/brands/haier.svg"
    assert data["brands"][1]["sort_order"] == 10
    assert [item["slug"] for item in data["expert_tags"]] == ["hit"]
    assert "wifi-builtin" not in [item["slug"] for item in data["expert_tags"]]


@pytest.mark.asyncio
async def test_filters_config_hides_obvious_pseudo_brands(async_client, db):
    brand_group = TagGroup(title="Brand", slug="brand")
    db.add(brand_group)
    await db.commit()
    await db.refresh(brand_group)

    valid_brand = Brand(title="TCL", slug="tcl", is_published=True)
    pseudo_brand = Brand(
        title="Мульти-сплит-система",
        slug="multi-split-sistema",
        is_published=True,
    )
    db.add(valid_brand)
    db.add(pseudo_brand)
    await db.flush()
    db.add(Product(title="A", slug="cfg-brand-a", price=1000, area=20, brand_id=valid_brand.id, is_published=True))
    await db.commit()

    response = await async_client.get("/api/v1/filters/config")
    assert response.status_code == 200
    data = response.json()

    slugs = [item["slug"] for item in data["brands"]]
    assert "tcl" in slugs
    assert "multi-split-sistema" not in slugs
