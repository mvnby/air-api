from types import SimpleNamespace

import pytest
from sqlmodel import select

from models import Brand, Product, ProductSeries, ProductTagLink, Tag, TagGroup
from services.brand_series_service import extract_series_name
from services.brand_series_service import sync_product_brand_series


def test_extract_series_name_from_specs():
    name = extract_series_name({"series": "Loft, Inverter"})
    assert name == "Loft"


def test_extract_series_name_from_russian_key():
    name = extract_series_name({"Серия": "BreezeIN 2.0"})
    assert name == "BreezeIN 2.0"


def test_extract_series_name_cleans_marketing_suffix_from_specs():
    assert extract_series_name({"series": "COSMO inverter R32 WI-FI"}) == "COSMO"
    assert extract_series_name({"series": "COSMO NORDIC inverter R32  WI-FI -25°C"}) == "COSMO NORDIC"
    assert extract_series_name({"series": "LUNA Matt inverter R32  WI-FI"}) == "LUNA Matt"


def test_extract_series_name_keeps_values_when_stop_marker_is_series_prefix():
    assert extract_series_name({"series": "R32 Deluxe"}) == "R32 Deluxe"
    assert extract_series_name({"series": "Wi-Fi Ready"}) == "Wi-Fi Ready"
    assert extract_series_name({"series": "COSMO inverter"}) == "COSMO"
    assert extract_series_name({"series": "Dual Inverter"}) == "Dual Inverter"
    assert extract_series_name({"series": "Dual Inverter R32 WI-FI"}) == "Dual Inverter"


def test_extract_series_name_supports_extended_russian_keys():
    name = extract_series_name({"Серия кондиционера": "VIOLA inverter R32 WI-FI"})
    assert name == "VIOLA"


def test_extract_series_name_from_series_tag_fallback():
    tag = SimpleNamespace(
        title="Elite",
        group=SimpleNamespace(slug="series"),
    )
    name = extract_series_name({}, [tag])
    assert name == "Elite"


def test_extract_series_name_from_title_after_brand_fallback():
    name = extract_series_name({}, title="KINGHOME Cosmo KWH24AWDXE-K6DNA3A", brand_name="KINGHOME")
    assert name == "Cosmo"


def test_extract_series_name_title_fallback_ignores_model_code_after_brand():
    name = extract_series_name({}, title="KINGHOME KUD100ZD1/A-S+ KUD100W1/NhA-S", brand_name="KINGHOME")
    assert name is None


def test_extract_series_name_title_fallback_keeps_series_version_and_inverter_word():
    assert (
        extract_series_name({}, title="TCL BreezeIN 2.0 A+++ TAC-09CHSD", brand_name="TCL")
        == "BreezeIN 2.0"
    )
    assert (
        extract_series_name({}, title="LG Dual Inverter S09EQ", brand_name="LG")
        == "Dual Inverter"
    )


def test_extract_series_name_title_fallback_stops_before_capacity_tokens():
    assert extract_series_name({}, title="Gree Bora 09 GWH09AAA-K6DNA1A", brand_name="Gree") == "Bora"
    assert extract_series_name({}, title="AUX Halo 12 ASW-H12A4", brand_name="AUX") == "Halo"
    assert (
        extract_series_name({}, title="Midea Xtreme Save 09 MSAG-09HRN8", brand_name="Midea")
        == "Xtreme Save"
    )


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
        specs={"area_m2": 30, "brand": "LG"},
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
        specs={"area_m2": 25},
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


@pytest.mark.asyncio
async def test_sync_product_brand_series_reports_brand_title_self_heal_once(db):
    brand_group = TagGroup(title="Brand", slug="brand", allow_multiple=False)
    brand = Brand(title="", slug="self-heal-brand")
    db.add_all([brand_group, brand])
    await db.flush()
    brand_tag = Tag(
        title="Self Heal Brand",
        slug="self-heal-brand",
        group_id=brand_group.id,
        is_public=True,
        is_filter=True,
    )
    product = Product(
        title="Self Heal Product",
        slug="self-heal-product",
        price=1000,
        brand_id=brand.id,
        specs={"brand": "Self Heal Brand"},
    )
    db.add_all([brand_tag, product])
    await db.flush()
    db.add(ProductTagLink(product_id=product.id, tag_id=brand_tag.id))
    await db.commit()

    first_changed = await sync_product_brand_series(
        db,
        product=product,
        specs=product.specs,
        title=product.title,
        allow_series_tag_fallback=False,
        allow_series_title_fallback=False,
    )
    await db.commit()
    second_changed = await sync_product_brand_series(
        db,
        product=product,
        specs=product.specs,
        title=product.title,
        allow_series_tag_fallback=False,
        allow_series_title_fallback=False,
    )

    await db.refresh(brand)
    assert first_changed is True
    assert second_changed is False
    assert brand.title == "Self Heal Brand"


@pytest.mark.asyncio
async def test_sync_product_brand_series_reports_orphan_series_attachment_once(db):
    brand_group = TagGroup(title="Brand", slug="brand", allow_multiple=False)
    brand = Brand(title="Series Heal Brand", slug="series-heal-brand")
    orphan = ProductSeries(title="Orphan Line", slug="orphan-line", brand_id=None)
    db.add_all([brand_group, brand, orphan])
    await db.flush()
    brand_tag = Tag(
        title=brand.title,
        slug=brand.slug,
        group_id=brand_group.id,
        is_public=True,
        is_filter=True,
    )
    product = Product(
        title="Series Heal Product",
        slug="series-heal-product",
        price=1000,
        brand_id=brand.id,
        series_id=orphan.id,
        specs={"brand": brand.title, "series": orphan.title},
    )
    db.add_all([brand_tag, product])
    await db.flush()
    db.add(ProductTagLink(product_id=product.id, tag_id=brand_tag.id))
    await db.commit()

    first_changed = await sync_product_brand_series(
        db,
        product=product,
        specs=product.specs,
        title=product.title,
    )
    await db.commit()
    second_changed = await sync_product_brand_series(
        db,
        product=product,
        specs=product.specs,
        title=product.title,
    )

    await db.refresh(orphan)
    assert first_changed is True
    assert second_changed is False
    assert orphan.brand_id == brand.id
