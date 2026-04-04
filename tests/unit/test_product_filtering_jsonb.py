import pytest

from crud.product import ProductDAO
from models import Product, ProductTagLink, Tag, TagGroup
from services.product_service import ProductService
from services.spec_normalizer import normalize_specs


@pytest.mark.asyncio
async def test_jsonb_filters_and_allowed_tag_groups(db):
    brand_group = TagGroup(title="Brand", slug="brand")
    category_group = TagGroup(title="Category", slug="category")
    expert_group = TagGroup(title="Expert", slug="expert-badge", is_expert_badge=True)
    technical_group = TagGroup(title="Tech", slug="wifi")
    db.add(brand_group)
    db.add(category_group)
    db.add(expert_group)
    db.add(technical_group)
    await db.commit()
    await db.refresh(brand_group)
    await db.refresh(category_group)
    await db.refresh(expert_group)
    await db.refresh(technical_group)

    brand_tag = Tag(title="Gree", slug="gree", group_id=brand_group.id, is_public=True)
    second_brand_tag = Tag(title="AUX", slug="aux", group_id=brand_group.id, is_public=True)
    category_household_tag = Tag(title="Бытовые", slug="cat-household", group_id=category_group.id, is_public=True)
    category_multi_tag = Tag(title="Мульти-сплит", slug="cat-multi", group_id=category_group.id, is_public=True)
    expert_tag = Tag(title="Тихий", slug="quiet-proven", group_id=expert_group.id, is_public=True)
    technical_tag = Tag(title="Wi-Fi встроен", slug="wifi-builtin", group_id=technical_group.id, is_public=True)
    db.add(brand_tag)
    db.add(second_brand_tag)
    db.add(category_household_tag)
    db.add(category_multi_tag)
    db.add(expert_tag)
    db.add(technical_tag)
    await db.commit()
    await db.refresh(brand_tag)
    await db.refresh(second_brand_tag)
    await db.refresh(category_household_tag)
    await db.refresh(category_multi_tag)
    await db.refresh(expert_tag)
    await db.refresh(technical_tag)

    p1 = Product(
        title="P1",
        slug="p1",
        price=1500,
        area=35,
        is_inverter=True,
        specs=normalize_specs({"temp_range_heat": "от -25 до +24", "wifi_ready": "да"}),
        is_published=True,
    )
    p2 = Product(
        title="P2",
        slug="p2",
        price=1200,
        area=25,
        is_inverter=False,
        specs=normalize_specs({"temp_range_heat": "от -10 до +24", "wifi_ready": "нет"}),
        is_published=True,
    )
    p3 = Product(
        title="P3",
        slug="p3",
        price=1800,
        area=45,
        is_inverter=True,
        specs=normalize_specs({"temp_range_heat": "от -22 до +24", "wifi_ready": "да"}),
        is_published=True,
    )
    db.add(p1)
    db.add(p2)
    db.add(p3)
    await db.commit()
    await db.refresh(p1)
    await db.refresh(p2)
    await db.refresh(p3)

    db.add_all(
        [
            ProductTagLink(product_id=p1.id, tag_id=brand_tag.id),
            ProductTagLink(product_id=p1.id, tag_id=category_household_tag.id),
            ProductTagLink(product_id=p1.id, tag_id=expert_tag.id),
            ProductTagLink(product_id=p1.id, tag_id=technical_tag.id),
            ProductTagLink(product_id=p2.id, tag_id=second_brand_tag.id),
            ProductTagLink(product_id=p2.id, tag_id=category_multi_tag.id),
            ProductTagLink(product_id=p2.id, tag_id=technical_tag.id),
            ProductTagLink(product_id=p3.id, tag_id=brand_tag.id),
            ProductTagLink(product_id=p3.id, tag_id=category_multi_tag.id),
        ]
    )
    await db.commit()

    filtered = await ProductDAO.get_filtered(
        db,
        heating_min=-20,
        has_wifi=True,
        is_inverter=True,
        area_max=40,
        tag_slugs=["gree"],
    )
    assert [p.slug for p in filtered] == ["p1"]

    # Technical tags are ignored for storefront filter compatibility.
    by_technical_slug = await ProductDAO.get_filtered(db, tag_slugs=["wifi-builtin"])
    assert {p.slug for p in by_technical_slug} == {"p1", "p2", "p3"}

    # OR within one group (brand), AND across groups (brand + category).
    grouped_legacy_filter = await ProductDAO.get_filtered(
        db,
        tag_slugs=["gree", "aux", "cat-multi"],
    )
    assert {p.slug for p in grouped_legacy_filter} == {"p2", "p3"}

    grouped_ids = await ProductService.resolve_slugs_to_grouped_ids(
        db, ["gree", "quiet-proven", "cat-multi", "wifi-builtin"]
    )
    flat_ids = {tag_id for tag_ids in grouped_ids.values() for tag_id in tag_ids}
    assert brand_tag.id in flat_ids
    assert category_multi_tag.id in flat_ids
    assert expert_tag.id in flat_ids
    assert technical_tag.id not in flat_ids
