from types import SimpleNamespace

import pytest
from sqlmodel import select

from models import Brand, Product, ProductTagLink, Tag, TagGroup
from services.brand_series_service import extract_series_name
from services.brand_series_service import sync_product_brand_series


def test_extract_series_name_from_specs():
    name = extract_series_name({"series": "Loft, Inverter"})
    assert name == "Loft"


def test_extract_series_name_from_russian_key():
    name = extract_series_name({"Серия": "BreezeIN 2.0"})
    assert name == "BreezeIN 2.0"


def test_extract_series_name_from_series_tag_fallback():
    tag = SimpleNamespace(
        title="Elite",
        group=SimpleNamespace(slug="series"),
    )
    name = extract_series_name({}, [tag])
    assert name == "Elite"


@pytest.mark.asyncio
async def test_sync_product_brand_series_prefers_manual_brand_tag_and_replaces_links(db):
    brand_group = TagGroup(title="Brand", slug="brand", allow_multiple=False)
    db.add(brand_group)
    await db.commit()
    await db.refresh(brand_group)

    lg_tag = Tag(title="LG", slug="lg", group_id=brand_group.id, is_public=True, is_filter=True)
    tcl_tag = Tag(title="TCL", slug="tcl", group_id=brand_group.id, is_public=True, is_filter=True)
    db.add(lg_tag)
    db.add(tcl_tag)
    await db.commit()
    await db.refresh(lg_tag)
    await db.refresh(tcl_tag)

    product = Product(
        title="LG Test Model",
        slug="lg-test-model-brand-sync",
        price=1200,
        area=30,
        specs={"brand": "LG"},
        is_published=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    db.add(ProductTagLink(product_id=product.id, tag_id=lg_tag.id))
    await db.commit()

    changed = await sync_product_brand_series(
        db,
        product=product,
        specs=product.specs or {},
        title=product.title,
        tags=[tcl_tag],  # selected in manager payload
    )
    assert changed is True
    await db.commit()

    brand = (await db.execute(select(Brand).where(Brand.id == product.brand_id))).scalar_one()
    assert brand.slug == "tcl"

    linked_brand_slugs = (
        await db.execute(
            select(Tag.slug)
            .join(ProductTagLink, ProductTagLink.tag_id == Tag.id)
            .where(ProductTagLink.product_id == product.id)
            .where(Tag.group_id == brand_group.id)
        )
    ).scalars().all()
    assert linked_brand_slugs == ["tcl"]


@pytest.mark.asyncio
async def test_sync_product_brand_series_works_without_loaded_tag_group(db):
    brand_group = TagGroup(title="Brand", slug="brand", allow_multiple=False)
    db.add(brand_group)
    await db.commit()
    await db.refresh(brand_group)

    tcl_tag = Tag(title="TCL", slug="tcl", group_id=brand_group.id, is_public=True, is_filter=True)
    db.add(tcl_tag)
    await db.commit()
    await db.refresh(tcl_tag)

    tag_without_group_loaded = (await db.execute(select(Tag).where(Tag.id == tcl_tag.id))).scalar_one()

    product = Product(
        title="Any Model",
        slug="any-model-no-group-loaded",
        price=1000,
        area=25,
        is_published=True,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)

    changed = await sync_product_brand_series(
        db,
        product=product,
        specs={},
        title=product.title,
        tags=[tag_without_group_loaded],
    )
    assert changed is True
