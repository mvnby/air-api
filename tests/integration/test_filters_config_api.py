import pytest

from models import Product, Tag, TagGroup


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

    brand = Tag(title="Haier", slug="haier", group_id=brand_group.id, is_public=True)
    expert = Tag(title="Хит", slug="hit", group_id=expert_group.id, is_public=True)
    technical = Tag(title="Wi-Fi", slug="wifi-builtin", group_id=technical_group.id, is_public=True)
    db.add(brand)
    db.add(expert)
    db.add(technical)

    p1 = Product(title="A", slug="a", price=1000, area=20, is_published=True)
    p2 = Product(title="B", slug="b", price=2400, area=55, is_published=True)
    db.add(p1)
    db.add(p2)
    await db.commit()

    response = await async_client.get("/api/v1/filters/config")
    assert response.status_code == 200
    data = response.json()

    assert data["price"] == {"min": 1000, "max": 2400}
    assert data["area"] == {"min": 20, "max": 55}
    assert [item["slug"] for item in data["brands"]] == ["haier"]
    assert [item["slug"] for item in data["expert_tags"]] == ["hit"]
    assert "wifi-builtin" not in [item["slug"] for item in data["expert_tags"]]
