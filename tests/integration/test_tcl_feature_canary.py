from pathlib import Path

import pytest
from sqlmodel import select

from models import (
    Brand,
    Feature,
    FeatureBrandLink,
    FeatureCategory,
    FeatureProductLink,
    FeatureSeriesLink,
    Product,
    ProductSeries,
)
from services.feature_resolver_service import FeatureResolverService
from services.tcl_feature_canary_service import (
    TclFeatureCanaryService,
    load_tcl_feature_canary_manifest,
)


MANIFEST = Path(__file__).parents[2] / "data/feature_canary/tcl_2026.json"


async def _seed(db):
    categories = [
        FeatureCategory(slug="comfort", name="Комфорт", sort_order=10),
        FeatureCategory(slug="control", name="Управление", sort_order=20),
        FeatureCategory(slug="air-quality", name="Очистка воздуха", sort_order=30),
        FeatureCategory(slug="efficiency", name="Энергоэффективность", sort_order=40),
        FeatureCategory(slug="performance", name="Производительность", sort_order=50),
        FeatureCategory(slug="heating", name="Обогрев", sort_order=60),
    ]
    brand = Brand(title="TCL", slug="tcl", is_published=True)
    db.add_all([*categories, brand])
    await db.flush()
    by_category = {item.slug: item for item in categories}

    legacy = [
        Feature(
            slug="vstroennyi-wi-fi",
            name="Встроенный Wi-Fi",
            category_id=by_category["comfort"].id,
            scope_type="brand",
            brand_id=brand.id,
        ),
        Feature(
            slug="bipoliarnyi-ionizator",
            name="Биполярный ионизатор",
            category_id=by_category["comfort"].id,
            scope_type="brand",
            brand_id=brand.id,
        ),
        Feature(
            slug="uf-sterilizatsiia",
            name="УФ-стерилизация",
            category_id=by_category["comfort"].id,
            scope_type="brand",
            brand_id=brand.id,
        ),
    ]
    db.add_all(legacy)
    await db.flush()
    db.add_all(
        FeatureBrandLink(brand_id=brand.id, feature_id=feature.id)
        for feature in legacy
    )

    series = {
        slug: ProductSeries(brand_id=brand.id, slug=slug, title=title, is_published=True)
        for slug, title in {
            "freshin3-0": "FreshIN 3.0",
            "breeze-in-2-0-a": "BreezeIN 2.0",
            "elite-inverter-c-paneliu-xa71n": "Elite Inverter",
            "elite-on": "Elite On/Off",
        }.items()
    }
    db.add_all(series.values())
    await db.flush()
    products = [
        Product(
            title="TCL Fresh In 3.0 TAC-09CHSD/FCI",
            slug="freshin-fci",
            price=1,
            brand_id=brand.id,
            series_id=series["freshin3-0"].id,
            is_inverter=True,
            specs={"compressor_type_norm": "inverter", "wifi_ready": True, "__filter_min_heat": -20},
        ),
        Product(
            title="TCL BreezeIN 2.0 TAC-09CHSD/UG11V3AH",
            slug="breeze-ug11",
            price=1,
            brand_id=brand.id,
            series_id=series["breeze-in-2-0-a"].id,
            is_inverter=True,
            specs={"compressor_type_norm": "inverter", "wifi_ready": False, "__filter_min_heat": -25},
        ),
        Product(
            title="TCL Elite TAC-09CHSD/XA71IN",
            slug="elite-xa71in",
            price=1,
            brand_id=brand.id,
            series_id=series["elite-inverter-c-paneliu-xa71n"].id,
            is_inverter=True,
            specs={"compressor_type_norm": "inverter", "wifi_ready": True, "__filter_min_heat": -20},
        ),
        Product(
            title="TCL Elite TAC-09CHSD/XA71IF",
            slug="elite-xa71if",
            price=1,
            brand_id=brand.id,
            series_id=series["elite-inverter-c-paneliu-xa71n"].id,
            is_inverter=True,
            specs={
                "compressor_type_norm": "inverter",
                "wifi_ready": False,
                "wifi_module": True,
                "__filter_min_heat": -10,
            },
        ),
        Product(
            title="TCL Elite TAC-09CHSA/XAB1N",
            slug="elite-xab1",
            price=1,
            brand_id=brand.id,
            series_id=series["elite-on"].id,
            is_inverter=False,
            specs={"compressor_type_norm": "on_off", "wifi_ready": False, "__filter_min_heat": -7},
        ),
    ]
    db.add_all(products)
    await db.flush()

    stale_smart_inverter = Feature(
        slug="smart-inverter-tcl",
        name="Smart Inverter",
        category_id=by_category["efficiency"].id,
        scope_type="brand",
        brand_id=brand.id,
    )
    stale_heating_20 = Feature(
        slug="heating-minus-20",
        name="Обогрев до −20 °C",
        category_id=by_category["performance"].id,
        scope_type="derived",
    )
    stale_heating_25 = Feature(
        slug="heating-minus-25",
        name="Обогрев до −25 °C",
        category_id=by_category["performance"].id,
        scope_type="derived",
    )
    db.add_all([stale_smart_inverter, stale_heating_20, stale_heating_25])
    await db.flush()
    db.add_all(
        [
            FeatureSeriesLink(
                series_id=series[series_slug].id,
                feature_id=stale_smart_inverter.id,
            )
            for series_slug in (
                "freshin3-0",
                "breeze-in-2-0-a",
                "elite-inverter-c-paneliu-xa71n",
            )
        ]
        + [
            FeatureProductLink(
                product_id=next(item.id for item in products if item.slug == "freshin-fci"),
                feature_id=stale_heating_20.id,
                source="derived",
            ),
            FeatureProductLink(
                product_id=next(item.id for item in products if item.slug == "breeze-ug11"),
                feature_id=stale_heating_25.id,
                source="derived",
            ),
        ]
    )
    await db.commit()
    return brand, products


@pytest.mark.asyncio
async def test_tcl_feature_canary_is_scoped_verified_and_idempotent(db):
    brand, products = await _seed(db)
    manifest = load_tcl_feature_canary_manifest(MANIFEST)

    first = await TclFeatureCanaryService(db, manifest).run(execute=True)
    await db.commit()

    assert first["actions"]
    assert first["cross_brand_violations"] == []
    assert first["duplicate_feature_ids"] == []
    assert first["unexpected_inheritance"] == []
    assert first["missing_expected_features"] == []
    assert first["unexpected_features"] == []
    assert first["unresolved_source_conflicts"] == []

    remaining_brand_links = list(
        (
            await db.execute(
                select(FeatureBrandLink).where(FeatureBrandLink.brand_id == brand.id)
            )
        ).scalars().all()
    )
    assert remaining_brand_links == []

    by_slug = {product.slug: product for product in products}
    await db.refresh(by_slug["elite-xa71in"])
    await db.refresh(by_slug["elite-xa71if"])
    assert by_slug["elite-xa71in"].specs["wifi_state"] == "builtin"
    assert by_slug["elite-xa71if"].specs["wifi_state"] == "ready"
    assert by_slug["elite-xa71in"].specs["__filter_min_heat"] == -15
    assert by_slug["elite-xa71if"].specs["__filter_min_heat"] == -15

    resolved = await FeatureResolverService.resolve_for_products(db, products)
    in_features = {item.slug for item in resolved[int(by_slug["elite-xa71in"].id)]["effective"]}
    if_features = {item.slug for item in resolved[int(by_slug["elite-xa71if"].id)]["effective"]}
    assert "vstroennyi-wi-fi" in in_features
    assert "wifi-ready" not in in_features
    assert "wifi-ready" in if_features
    assert "vstroennyi-wi-fi" not in if_features

    uvc = (await db.execute(select(Feature).where(Feature.slug == "uf-sterilizatsiia"))).scalar_one()
    assert uvc.scope_type == "universal"
    assert uvc.brand_id is None
    builtin_wifi = (
        await db.execute(select(Feature).where(Feature.slug == "vstroennyi-wi-fi"))
    ).scalar_one()
    assert builtin_wifi.scope_type == "derived"
    assert builtin_wifi.brand_id is None
    heating = (
        await db.execute(select(Feature).where(Feature.slug == "low-temperature-heating"))
    ).scalar_one()
    heating_category = await db.get(FeatureCategory, heating.category_id)
    assert heating_category.slug == "heating"
    smart_inverter = (
        await db.execute(select(Feature).where(Feature.slug == "smart-inverter-tcl"))
    ).scalar_one()
    assert smart_inverter.is_active is False
    assert smart_inverter.archived_at is not None
    stale_series_links = list(
        (
            await db.execute(
                select(FeatureSeriesLink).where(
                    FeatureSeriesLink.feature_id == smart_inverter.id
                )
            )
        ).scalars().all()
    )
    assert stale_series_links == []
    stale_heating_ids = list(
        (
            await db.execute(
                select(Feature.id).where(
                    Feature.slug.in_(("heating-minus-20", "heating-minus-25"))
                )
            )
        ).scalars().all()
    )
    stale_heating_links = list(
        (
            await db.execute(
                select(FeatureProductLink).where(
                    FeatureProductLink.feature_id.in_(stale_heating_ids)
                )
            )
        ).scalars().all()
    )
    assert stale_heating_links == []
    breeze = by_slug["breeze-ug11"]
    freshin = by_slug["freshin-fci"]
    breeze_links = set(
        (
            await db.execute(
                select(FeatureProductLink.feature_id).where(FeatureProductLink.product_id == breeze.id)
            )
        ).scalars().all()
    )
    assert uvc.id not in breeze_links  # Series inheritance, not a duplicated product link.
    freshin_features = {item.slug for item in resolved[int(freshin.id)]["effective"]}
    assert "uf-sterilizatsiia" not in freshin_features
    assert "gentle-breeze" not in freshin_features

    second = await TclFeatureCanaryService(db, manifest).run(execute=True)
    await db.commit()
    assert second["actions"] == []


@pytest.mark.asyncio
async def test_tcl_feature_canary_dry_run_can_be_rolled_back(db):
    await _seed(db)
    manifest = load_tcl_feature_canary_manifest(MANIFEST)
    transaction = await db.begin_nested()
    report = await TclFeatureCanaryService(db, manifest).run(execute=False)
    assert report["mode"] == "dry-run"
    assert report["actions"]
    await transaction.rollback()

    created = (
        await db.execute(select(Feature).where(Feature.slug == "freshin-plus"))
    ).scalar_one_or_none()
    assert created is None
