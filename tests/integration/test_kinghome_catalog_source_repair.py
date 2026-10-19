"""Exercise the actual CLI transaction and outbox against isolated PostgreSQL."""

from copy import deepcopy
import json
import re
from urllib.parse import quote

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.catalog_revision import CatalogRevisionDAO
from models import Brand, IntegrationOutboxEvent, Product, ProductSeries
from scripts.repair_kinghome_catalog import run
from services.catalog_invalidation_contracts import CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
from services.catalog_kinghome_source_repair import digest, load_manifest
from services.catalog_revision_service import CatalogRevisionService


def _fixture_catalog():
    manifest = deepcopy(load_manifest())
    manifest["sources"]["integration_fixture"] = True
    products, series = [], []
    for row in manifest["products"]:
        before = row["before"]
        specs = {
            key: deepcopy(cell["value"])
            for section in ("specs", "filters")
            for key, cell in before[section].items()
            if cell["present"]
        }
        specs["__typed_specs"] = {
            key: deepcopy(cell["value"])
            for key, cell in before["typed"].items()
            if cell["present"]
        }
        specs["fixture_unrelated"] = {"keep": [row["identity"]["id"], "exact"]}
        specs["__filter_fixture_unrelated"] = 901
        specs["__typed_specs"]["fixture_unrelated"] = {"value": "preserve"}
        # The checked-in manifest deliberately stores original prose as hashes.
        # Give the fixture known preimages without copying production prose.
        description = f"Original fixture product {row['identity']['id']}"
        before["fields_sha256"] = {
            key: digest(description) for key in before["fields_sha256"]
        }
        row["source_before_sha256"] = digest(before)
        products.append(Product(
            **row["identity"], specs=specs, description=description,
            price=1000 + row["identity"]["id"], product_kind="other",
            main_image="https://example.invalid/preserve.webp",
        ))
    for row in manifest["series"]:
        fields = {
            "description": f"Original fixture series {row['identity']['id']}",
            "short_description": "Original fixture short description",
            "content_blocks": [], "feature_blocks": [],
        }
        row["before_sha256"] = {
            key: digest(fields[key]) for key in row["before_sha256"]
        }
        series.append(ProductSeries(
            **row["identity"], **fields, seo_title="Preserve SEO",
            hero_image="https://example.invalid/preserve-series.webp",
        ))
    return manifest, Brand(**manifest["brand"]), products, series


async def _snapshot(factory):
    async with factory() as session:
        products = (await session.execute(select(Product).order_by(Product.id))).scalars().all()
        series = (await session.execute(select(ProductSeries).order_by(ProductSeries.id))).scalars().all()
        events = (await session.execute(
            select(IntegrationOutboxEvent).where(
                IntegrationOutboxEvent.event_type == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
            ).order_by(IntegrationOutboxEvent.event_id)
        )).scalars().all()
        revision = await CatalogRevisionDAO.get_current(session)
        return deepcopy({
            "products": {p.id: {key: getattr(p, key) for key in (
                "title", "brand_id", "series_id", "specs", "description",
                "price", "product_kind", "main_image",
            )} for p in products},
            "series": {s.id: {key: getattr(s, key) for key in (
                "description", "short_description", "content_blocks",
                "feature_blocks", "seo_title", "hero_image",
            )} for s in series},
            "revision": revision.revision,
            "events": [{"event_id": e.event_id, "payload": e.payload, "status": e.status} for e in events],
        })


@pytest.mark.asyncio
async def test_cli_repair_rolls_back_staged_writes_commits_once_and_repeats_as_noop(
    db_engine, monkeypatch, tmp_path,
):
    assert db_engine.dialect.name == "postgresql"
    assert re.search(r"(?:^|_)test(?:_|$)", db_engine.url.database)
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    import core.database
    monkeypatch.setattr(core.database, "async_session_maker", factory)
    manifest, brand, products, series = _fixture_catalog()
    manifest_path = tmp_path / "kinghome-fixture-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    async with factory() as session:
        session.add(brand)
        await session.flush()
        session.add_all(series)
        await session.flush()
        session.add_all(products)
        await session.commit()

    baseline = await _snapshot(factory)
    assert len(baseline["products"]) == 42 and len(baseline["series"]) == 9
    assert baseline["revision"] == 0 and baseline["events"] == []
    reviewed = await run(manifest_path=manifest_path)
    assert reviewed["ready"] is True and reviewed["changed"] == 43
    assert await _snapshot(factory) == baseline  # Default CLI path is read-only.
    reviewed_path = tmp_path / "reviewed-plan.json"
    reviewed_path.write_text(json.dumps(reviewed, ensure_ascii=False), encoding="utf-8")

    real_staging = CatalogRevisionService.stage_invalidation
    staging_reached = []

    async def fail_after_real_staging(session, **kwargs):
        staged = await real_staging(session, **kwargs)
        staged_product = await session.get(Product, 1301)
        assert staged_product.specs["__filter_noise_min"] == 34
        assert staged["revision"] == 1
        staged_events = (await session.execute(select(IntegrationOutboxEvent))).scalars().all()
        assert len(staged_events) == 1
        staging_reached.append(True)
        raise RuntimeError("fixture failure after real revision/outbox staging")

    with monkeypatch.context() as failure:
        failure.setattr(CatalogRevisionService, "stage_invalidation", fail_after_real_staging)
        with pytest.raises(RuntimeError, match="after real revision/outbox staging"):
            await run(
                manifest_path=manifest_path, execute=True,
                reviewed_plan=reviewed_path, execute_plan_digest=reviewed["plan_digest"],
            )
    assert staging_reached == [True]
    assert await _snapshot(factory) == baseline  # Business rows, revision and event rolled back.

    result = await run(
        manifest_path=manifest_path, execute=True,
        reviewed_plan=reviewed_path, execute_plan_digest=reviewed["plan_digest"],
    )
    assert result["changed"] == 43 and result["revision"]["revision"] == 1
    after = await _snapshot(factory)
    assert after["revision"] == 1 and len(after["events"]) == 1
    event = after["events"][0]
    assert event["status"] == "pending"
    assert event["payload"]["reason"] == "kinghome_source_catalog_repair"
    assert event["payload"]["global_revision"] == 1
    expected_paths = {
        f"/product/{quote(row['identity']['slug'], safe='')}/"
        for row in manifest["products"]
    } | set(reviewed["series_paths"]) | {"/brands/kinghome/", "/brands/", "/catalog/"}
    assert set(event["payload"]["paths"]) == expected_paths
    assert len(reviewed["series_paths"]) == 9
    for id, product in after["products"].items():
        original = baseline["products"][id]
        for key in ("price", "product_kind", "main_image", "title", "brand_id", "series_id"):
            assert product[key] == original[key]
        for key in ("fixture_unrelated", "__filter_fixture_unrelated"):
            assert product["specs"][key] == original["specs"][key]
        assert product["specs"]["__typed_specs"]["fixture_unrelated"] == {"value": "preserve"}
    for id, item in after["series"].items():
        for key in ("content_blocks", "feature_blocks", "seo_title", "hero_image"):
            assert item[key] == baseline["series"][id][key]
    assert after["products"][1309]["specs"]["height_indoor"] == "300"
    for id, height in [(1301, "200"), (1304, "290")]:
        specs = after["products"][id]["specs"]
        assert specs["height_indoor"] == height
        assert specs["__typed_specs"]["height_indoor"]["value"] == int(height)
        assert specs["width_indoor"] == specs["depth_indoor"] == "840"
    assert "ionizer" not in after["products"][764]["specs"]

    noop = await run(manifest_path=manifest_path)
    assert noop["changed"] == 0
    reviewed_path.write_text(json.dumps(noop, ensure_ascii=False), encoding="utf-8")
    repeated = await run(
        manifest_path=manifest_path, execute=True,
        reviewed_plan=reviewed_path, execute_plan_digest=noop["plan_digest"],
    )
    assert repeated["changed"] == 0 and repeated["revision"] is None
    assert await _snapshot(factory) == after
