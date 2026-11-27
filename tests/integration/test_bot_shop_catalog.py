"""Check the shop through Telegram's actual actor/context guard and PostgreSQL."""

from datetime import datetime, timezone
from time import perf_counter
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from models import (
    Brand, Feature, FeatureCategory, FeatureProductLink, FeatureRule, FeatureSeriesLink,
    Product, ProductImage, ProductImageVariant, ProductSeries, StaffUser, Storefront,
    Tenant, TenantCatalogGrant, TenantMembership, TenantOffer,
)
from models.supplier import ProductLocalStock
from models.tenancy import StorefrontDomain
from routers.internal_bot_context import router as context_router
from routers.internal_bot_shop import router as shop_router
from services.fx_rate_service import FxRateService


SHOP = "/api/internal/bot/v1/shop"
PARTNER = {"telegram_id": 72401, "expected_context_version": 0}
SYSTEM = {"telegram_id": 72402, "expected_context_version": 0}
CDN = "https://cdn.mvn.by/products"
ORIGINAL = f"{CDN}/variants/original/echo.webp"
THUMB = f"{CDN}/variants/card/echo.webp"
FULL = f"{CDN}/variants/full/echo.webp"


@pytest.fixture
async def shop(db_engine, monkeypatch):
    monkeypatch.setattr(settings, "BOT_API_TOKEN", "test-shop-token")
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://mvn.by")
    monkeypatch.setattr(FxRateService, "get_supplier_usd_byn_rate", AsyncMock(side_effect=AssertionError(
        "Customer-facing catalog reads must not fetch wholesale exchange rates"
    )))
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        partner = Tenant(slug="shop-partner", display_name="Partner", demo_read_only=True)
        db.add(partner)
        await db.flush()
        sites = [Storefront(tenant_id=partner.id, slug=slug, display_name=slug, status="active", is_default=i == 0)
                 for i, slug in enumerate(("principal", "other"))]
        db.add_all(sites)
        await db.flush()
        db.add(StorefrontDomain(storefront_id=sites[0].id, hostname="shop-partner.test", is_primary=True,
                                status="active", verified_at=datetime.now(timezone.utc)))
        for tgid, tenant_id, role in ((72401, partner.id, "manager"), (72402, 1, "manager"), (72403, 1, "installer")):
            staff = StaffUser(display_name=str(tgid), telegram_id=tgid, primary_role=role, roles=[role])
            db.add(staff)
            await db.flush()
            db.add(TenantMembership(tenant_id=tenant_id, staff_user_id=staff.id, role=role))

        brands = {key: Brand(title=key, slug=key.lower()) for key in ("Alpha", "Beta", "Private")}
        db.add_all(brands.values())
        await db.flush()
        series = {key: ProductSeries(title=f"{key} line", slug=key.lower(), brand_id=brand.id)
                  for key, brand in brands.items()}
        db.add_all(series.values())
        await db.flush()
        data = [
            ("one", "Alpha", 2.2, 22), ("two", "Alpha", 2.6, 28), ("three", "Alpha", 3.5, 35),
            ("orderable", "Beta", None, 29), ("other_site", "Private", 2.6, 25),
            ("disabled", "Private", 2.6, 26), ("ungranted", "Private", 2.6, 27),
            ("draft", "Private", 3.6, 34), ("component", "Private", 3.6, 35), ("missing", "Private", 3.6, 35),
        ]
        products = {}
        for index, (key, brand, power, area) in enumerate(data, 1):
            specs = {"area_m2": area}
            if brand == "Alpha":
                specs.update(wifi_state="builtin", indoor_type="настенный", __filter_min_heat=-25)
            elif key == "orderable":
                specs.update(__typed_specs={"wifi_state": {"value": "ready"}}, indoor_type="кассетный")
            if key == "one":
                specs.update(__supplier_secret="DO_NOT_DISCLOSE", vendor_notes="DO_NOT_DISCLOSE")
            product = Product(
                title=f"{index:02d} Echo {key}", slug=f"echo-{key}", price=index * 10 + 900,
                brand_id=brands[brand].id, series_id=series[brand].id, is_inverter=brand == "Alpha",
                product_kind="complete_split_system", power_cooling=power, is_published=key != "draft", specs=specs,
                main_image="/media/products/shared/echo.webp" if key == "one" else None,
                description="<p>Тихая модель</p><script>DO_NOT_DISCLOSE</script>" if key == "one" else "",
                images=["/media/legacy.webp", "https://supplier.invalid/private.webp"] if key == "one" else [],
                source_url="https://supplier.invalid/DO_NOT_DISCLOSE",
            )
            if key == "component":
                product.specs = {"type": "внутренний блок"}
            products[key] = product
        db.add_all(products.values())
        await db.flush()
        for key, product in products.items():
            if key != "orderable":
                db.add(ProductLocalStock(product_id=product.id, qty=3))
        grants = [
            TenantCatalogGrant(tenant_id=partner.id, storefront_id=site.id, status="active",
                               created_by_username="test", updated_by_username="test")
            for site in sites
        ]
        db.add_all(grants)
        await db.flush()
        for index, (key, product) in enumerate(products.items()):
            if key == "missing":
                continue
            site_index = int(key == "other_site")
            db.add(TenantOffer(
                tenant_id=partner.id, storefront_id=sites[site_index].id, product_id=product.id,
                catalog_grant_id=None if key == "ungranted" else grants[site_index].id,
                status="disabled" if key == "disabled" else "active", is_published=True,
                price=2200 if key in ("one", "three") else 1800 + index * 100,
                created_by_username="test", updated_by_username="test",
            ))

        category = FeatureCategory(name="Комфорт", slug="comfort")
        db.add(category)
        await db.flush()
        features = {name: Feature(name=name, slug=name.lower(), category_id=category.id)
                    for name in ("Quiet", "Wifi", "Purifier", "Secret")}
        db.add_all(features.values())
        await db.flush()
        branded = Feature(name="Alpha Plasma", slug="alpha-plasma", category_id=category.id, scope_type="brand",
                          brand_id=brands["Alpha"].id, replaces_feature_id=features["Purifier"].id)
        db.add(branded)
        await db.flush()
        features["Plasma"] = branded
        db.add_all([
            FeatureSeriesLink(series_id=series["Alpha"].id, feature_id=features["Quiet"].id),
            FeatureSeriesLink(series_id=series["Alpha"].id, feature_id=features["Purifier"].id),
            FeatureProductLink(product_id=products["two"].id, feature_id=features["Quiet"].id, is_enabled=False),
            FeatureProductLink(product_id=products["one"].id, feature_id=branded.id),
            FeatureProductLink(product_id=products["other_site"].id, feature_id=features["Secret"].id),
            FeatureRule(feature_id=features["Wifi"].id, spec_key="wifi_state", operator="eq", target_value="builtin"),
        ])
        image = ProductImage(product_id=products["one"].id, url="/media/products/shared/echo.webp")
        db.add(image)
        await db.flush()
        for kind, link in (("card", THUMB), ("full", FULL), ("original", ORIGINAL)):
            db.add(ProductImageVariant(product_image_id=image.id, variant_type=kind, url=link,
                                       processing_status="ready", manual_quality_status="approved"))
        await db.commit()

    app = FastAPI()
    app.include_router(context_router)
    app.include_router(shop_router)

    async def scoped_db():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = scoped_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"Authorization": "Bearer test-shop-token"}) as client:
        yield client, products, brands, series, features, partner


async def test_selected_storefront_scopes_stock_price_counts_and_every_detail(shop):
    client, products, brands, _, _, partner = shop
    base = await client.post(f"{SHOP}/browse", json=PARTNER)
    assert base.status_code == 200, base.text
    assert base.json()["meta"] == {"total": 3, "pages": 1, "limit": 20, "page": 1}
    assert [p["id"] for p in base.json()["items"]] == [products[k].id for k in ("one", "two", "three")]
    request = {**PARTNER, "filters": {"availability": "all"}}
    broad = (await client.post(f"{SHOP}/browse", json=request)).json()
    assert broad["meta"]["total"] == 4
    assert broad["items"][0]["retail_price_byn"] == 2200
    assert broad["items"][0]["public_site_url"] == "https://shop-partner.test/product/echo-one/"
    ids = [products[key].id for key in ("orderable", "missing", "one", "draft", "disabled", "component", "ungranted")]
    resolved = await client.post(f"{SHOP}/products/resolve", json={**PARTNER, "product_ids": ids})
    assert resolved.status_code == 200
    assert [row["id"] for row in resolved.json()["items"]] == [products["orderable"].id, products["one"].id]
    assert resolved.json()["items"][0]["availability"] == "out_of_stock"
    assert resolved.json()["items"][1]["thumbnail_url"] == THUMB
    system = await client.post(f"{SHOP}/products/{products['one'].id}", json=SYSTEM)
    assert system.json()["retail_price_byn"] == products["one"].price
    for key in ("other_site", "disabled", "ungranted", "draft", "component", "missing"):
        assert (await client.post(f"{SHOP}/products/{products[key].id}", json=PARTNER)).status_code == 404
    empty = (await client.post(f"{SHOP}/facets", json={**PARTNER, "filters": {"search": "nonexistent"}})).json()
    assert empty == {"total": 0, "brands": [], "series": [], "cooling_btu_classes": [], "features": []}
    assert (await client.post(f"{SHOP}/browse", headers={"Authorization": ""}, json=PARTNER)).status_code == 401
    assert (await client.post(f"{SHOP}/facets", json={**PARTNER, "telegram_id": 72403})).status_code == 403
    switched = await client.post("/api/internal/bot/v1/staff/context/select",
                                 json={**PARTNER, "tenant_id": partner.id, "storefront_slug": "other"})
    assert switched.status_code == 200
    assert (await client.post(f"{SHOP}/facets", json=PARTNER)).status_code == 409
    current = {**PARTNER, "expected_context_version": 1}
    facets = (await client.post(f"{SHOP}/facets", json=current)).json()
    assert [(b["id"], b["count"]) for b in facets["brands"]] == [(brands["Private"].id, 1)]
    assert [f["title"] for f in facets["features"]] == ["Secret"]
    assert (await client.post(f"{SHOP}/products/{products['one'].id}", json=current)).status_code == 404


async def test_real_features_apply_overrides_and_replacements_before_pagination(shop):
    client, products, brands, series, features, _ = shop
    common = {"search": "Echo", "availability": "all", "is_inverter": True,
              "brand_ids": [brands["Alpha"].id], "series_ids": [series["Alpha"].id], "wifi": "builtin",
              "cooling_btu_classes": [7, 9, 12], "area_min": 20, "area_max": 35, "heating_min": -25,
              "cooling_min_kw": 2.0, "cooling_max_kw": 3.6, "indoor_form_factor": "wall",
              "retail_min_byn": 1800, "retail_max_byn": 2300,
              "feature_ids": [features["Quiet"].id, features["Wifi"].id]}
    request = {**PARTNER, "filters": common, "limit": 1, "sort": "retail_price"}
    for page, expected in ((1, ["one"]), (2, ["three"]), (3, [])):
        response = await client.post(f"{SHOP}/browse", json={**request, "page": page})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["meta"] == {"page": page, "limit": 1, "total": 2, "pages": 2}
        assert [item["id"] for item in result["items"]] == [products[k].id for k in expected]
    facets = (await client.post(f"{SHOP}/facets", json={**PARTNER, "filters": common})).json()
    assert facets["total"] == 2
    assert [(b["id"], b["count"]) for b in facets["brands"]] == [(brands["Alpha"].id, 2)]
    assert facets["cooling_btu_classes"] == [{"value": 7, "count": 1}, {"value": 12, "count": 1}]
    assert {f["title"]: f["count"] for f in facets["features"]} == {
        "Quiet": 2, "Wifi": 2, "Purifier": 1, "Alpha Plasma": 1,
    }
    for feature, expected in (("Purifier", "three"), ("Plasma", "one")):
        filters = {**common, "feature_ids": [*common["feature_ids"], features[feature].id]}
        result = (await client.post(f"{SHOP}/browse", json={**request, "filters": filters})).json()
        assert [r["id"] for r in result["items"]] == [products[expected].id]
    no_match = (await client.post(f"{SHOP}/browse", json={
        **PARTNER, "filters": {"feature_ids": [features["Secret"].id]},
    })).json()
    assert no_match["items"] == [] and no_match["meta"]["total"] == 0


async def test_facets_use_nominal_btu_then_area_and_public_wifi_state(shop):
    client, products, _, _, _, _ = shop
    result = (await client.post(f"{SHOP}/browse", json={
        **PARTNER, "filters": {"availability": "all", "wifi": "ready", "cooling_btu_classes": [9]},
    })).json()
    assert [(i["id"], i["wifi"], i["cooling_power_kw"]) for i in result["items"]] == [
        (products["orderable"].id, "ready", None),
    ]
    facets = (await client.post(f"{SHOP}/facets", json={**PARTNER, "filters": {"availability": "all"}})).json()
    assert {b["title"]: b["count"] for b in facets["brands"]} == {"Alpha": 3, "Beta": 1}
    assert {f["value"]: f["count"] for f in facets["cooling_btu_classes"]} == {7: 1, 9: 2, 12: 1}
    filters = {"availability": "all", "cooling_btu_classes": [9]}
    choices = (await client.post(f"{SHOP}/facets", json={**PARTNER, "filters": filters})).json()
    assert choices["total"] == 2 and choices["cooling_btu_classes"] == facets["cooling_btu_classes"]
    assert (await client.post(f"{SHOP}/browse", json={**PARTNER, "filters": {"retail_min_byn": 21, "retail_max_byn": 20}})).status_code == 422
    assert (await client.post(f"{SHOP}/browse", json={**PARTNER, "sort": "purchase_cost"})).status_code == 422
    assert (await client.post(f"{SHOP}/products/resolve", json={**PARTNER, "product_ids": [1, 1]})).status_code == 422


async def test_shop_detail_has_distinct_approved_thumbnail_and_safe_complete_specifications(shop):
    client, products, _, _, _, _ = shop
    response = await client.post(f"{SHOP}/products/{products['one'].id}", json=PARTNER)
    assert response.status_code == 200, response.text
    card = response.json()
    assert card["description"] == "Тихая модель"
    assert card["thumbnail_url"] == THUMB
    assert [(img["url"], img["thumbnail_url"]) for img in card["images"]] == [
        (FULL, THUMB), ("https://mvn.by/media/legacy.webp", "https://mvn.by/media/legacy.webp"),
    ]
    assert {feature["title"] for feature in card["features"]} == {"Quiet", "Wifi", "Alpha Plasma"}
    fields = {f["key"]: f for group in card["specification_groups"] for f in group["items"]}
    assert fields["area_m2"]["value"] == "22" and fields["area_m2"]["unit"] == "м²"
    assert "capacity_cooling_kw" in fields and any(f["key"] == "area_m2" for f in card["summary_fields"])
    for secret in ("DO_NOT_DISCLOSE", "supplier", "purchase_cost", "margin", "recommended_price", "vendor_notes"):
        assert secret not in response.text


async def test_large_shop_feature_selection_keeps_order_and_queries_in_batches(shop, db_engine, record_property):
    client, _, brands, series, features, _ = shop
    names = (
        "eco", "dry", "sleep", "turbo", "auto_restart", "timer", "ionizer", "air_purifier",
        "self_clean", "quiet", "fresh_air", "child_lock", "display", "warm_start", "auto_defrost",
        "self_diagnosis", "i_feel", "vertical_swing", "horizontal_swing", "filter", "power_limit",
        "memory", "light_sensor", "humidity_control",
    )
    matches = {5, 129, 895, 1484, 1500}
    async with AsyncSession(db_engine, expire_on_commit=False) as db:
        feature_rows = [Feature(slug=f"bulk-{name}", name=name, category_id=features["Quiet"].category_id)
                        for name in names]
        db.add_all(feature_rows)
        await db.flush()
        db.add_all(FeatureRule(feature_id=feature.id, spec_key=name, operator="eq", target_value=True)
                   for name, feature in zip(names, feature_rows))
        records = []
        for index in range(1536):
            brand = "Alpha" if index % 2 else "Beta"
            specs = {name: (index % (i + 2) == 0) for i, name in enumerate(names)}
            specs.update(area_m2=25, capacity_cooling_kw=2.6, wifi_state="builtin" if index in matches else "ready",
                         __typed_specs={"capacity_cooling_kw": {"value": 2.6, "raw": "2,6 кВт"},
                                        "temp_range_heat": {"min": -25, "max": 18}})
            records.append(Product(title=f"Batchshop {index:04d}", slug=f"batchshop-{index}", price=1500 + index // 128,
                                   product_kind="complete_split_system", brand_id=brands[brand].id,
                                   series_id=series[brand].id, is_inverter=True, is_published=True, specs=specs))
        db.add_all(records)
        await db.commit()
        ordered = [records[i].id for i in sorted(matches, key=lambda i: (-records[i].price, records[i].id))]

    sql_counts = 0
    def count_statements(*_args):
        nonlocal sql_counts
        sql_counts += 1

    async def measure(path, payload):
        nonlocal sql_counts
        sql_counts = 0
        start = perf_counter()
        response = await client.post(f"{SHOP}/{path}", json={**SYSTEM, **payload})
        record_property(f"{path}_duration", round(perf_counter() - start, 3))
        record_property(f"{path}_statements", sql_counts)
        assert response.status_code == 200, response.text
        # Includes Telegram actor/context reads. Growth must be by batch, not by model.
        assert sql_counts < 110
        return response.json()

    event.listen(db_engine.sync_engine, "before_cursor_execute", count_statements)
    try:
        filters = {"availability": "all", "search": "batchshop"}
        out = await measure("facets", {"filters": filters})
        assert out["total"] == 1536
        counts = {f["slug"]: f["count"] for f in out["features"]}
        assert counts["wifi"] == len(matches) and counts["bulk-eco"] == 768
        page = await measure("browse", {
            "filters": {**filters, "feature_ids": [features["Wifi"].id]}, "sort": "retail_price",
            "direction": "desc", "limit": 2, "page": 2,
        })
        assert page["meta"] == {"total": len(matches), "page": 2, "pages": 3, "limit": 2}
        assert [item["id"] for item in page["items"]] == ordered[2:4]
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", count_statements)
