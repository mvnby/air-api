"""Exercise guarded CLI writes, rollback and invalidation on isolated PostgreSQL."""

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
from scripts.repair_catalog_power_supply import run
from services.catalog_invalidation_contracts import CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT
from services.catalog_power_supply_repair import RepairBlocked, load_manifest
from services.catalog_revision_service import CatalogRevisionService


async def snapshot(factory):
    async with factory() as session:
        products = list((await session.execute(select(Product).order_by(Product.id))).scalars())
        events = list((await session.execute(select(IntegrationOutboxEvent).where(
            IntegrationOutboxEvent.event_type == CATALOG_CACHE_INVALIDATION_REQUESTED_EVENT,
        ).order_by(IntegrationOutboxEvent.event_id))).scalars())
        revision = await CatalogRevisionDAO.get_current(session)
        return deepcopy({
            "products": {product.id: {key: getattr(product, key) for key in (
                "title", "slug", "brand_id", "series_id", "product_kind", "source_url",
                "specs", "price", "description", "main_image",
            )} for product in products},
            "revision": revision.revision,
            "events": [{"event_id": event.event_id, "status": event.status, "payload": event.payload} for event in events],
        })


@pytest.mark.asyncio
async def test_cli_guards_rollback_preserve_unrelated_values_and_commit_one_outbox_event(
    db_engine, monkeypatch, tmp_path,
):
    assert db_engine.dialect.name == "postgresql"
    assert re.search(r"(?:^|_)test(?:_|$)", db_engine.url.database)
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    import core.database
    monkeypatch.setattr(core.database, "async_session_maker", factory)
    manifest = load_manifest()
    async with factory() as session:
        session.add_all(Brand(**identity) for identity in manifest["brands"])
        await session.flush()
        series = {row["identity"]["series_id"]: row["identity"]["brand_id"] for row in manifest["products"] if row["identity"]["series_id"] is not None}
        session.add_all(ProductSeries(id=id, brand_id=brand_id, title=f"Fixture series {id}", slug=f"power-fixture-series-{id}") for id, brand_id in series.items())
        await session.flush()
        for row in manifest["products"]:
            specs = {
                **deepcopy(row["before"]["specs"]),
                "__typed_specs": {**deepcopy(row["before"]["typed"]), "unrelated": {"value": "exact"}},
                "unrelated": {"keep": [row["identity"]["id"], 902]},
                "__filter_unrelated": 12, "power_cons_cooling_kw": "3.999",
                "type": "preserve existing type", "type_tags": ["preserve", "exact"],
            }
            session.add(Product(
                **row["identity"], specs=specs, price=1000 + row["identity"]["id"],
                description="Preserve existing description", main_image="https://example.invalid/preserve.webp",
            ))
        await session.commit()

    baseline = await snapshot(factory)
    reviewed = await run()
    assert reviewed["ready"] and reviewed["changed"] == 82
    assert await snapshot(factory) == baseline
    reviewed_path = tmp_path / "reviewed.json"
    reviewed_path.write_text(json.dumps(reviewed))

    # An extra power alias after review is refused before any business/event write.
    async with factory() as session:
        product = await session.get(Product, 179)
        product.specs = {**product.specs, "Электропитание": "unreviewed new supplier value"}
        await session.commit()
    drifted = await snapshot(factory)
    with pytest.raises(RepairBlocked, match="power fields"):
        await run(execute=True, reviewed_plan=reviewed_path, execute_plan_digest=reviewed["plan_digest"])
    assert await snapshot(factory) == drifted
    async with factory() as session:
        product = await session.get(Product, 179)
        product.specs = deepcopy(baseline["products"][179]["specs"])
        # A concurrent unrelated change is deliberately retained by execution.
        product.price = 6789
        await session.commit()
    baseline = await snapshot(factory)

    real_staging = CatalogRevisionService.stage_invalidation
    reached = []

    async def fail_after_real_staging(session, **kwargs):
        revision = await real_staging(session, **kwargs)
        product = await session.get(Product, 179)
        assert "380-415" in product.specs["power_supply_outdoor"]
        assert "Напряжение, В" not in product.specs
        assert revision["revision"] == 1
        assert len(list((await session.execute(select(IntegrationOutboxEvent))).scalars())) == 1
        reached.append(True)
        raise RuntimeError("fixture error after actual outbox staging")

    with monkeypatch.context() as failing:
        failing.setattr(CatalogRevisionService, "stage_invalidation", fail_after_real_staging)
        with pytest.raises(RuntimeError, match="actual outbox staging"):
            await run(execute=True, reviewed_plan=reviewed_path, execute_plan_digest=reviewed["plan_digest"])
    assert reached == [True]
    assert await snapshot(factory) == baseline

    result = await run(execute=True, reviewed_plan=reviewed_path, execute_plan_digest=reviewed["plan_digest"])
    assert result["changed"] == 82 and result["revision"]["revision"] == 1
    after = await snapshot(factory)
    assert after["revision"] == 1 and len(after["events"]) == 1
    event = after["events"][0]
    assert event["status"] == "pending"
    assert event["payload"]["reason"] == "catalog_power_supply_repair"
    assert event["payload"]["global_revision"] == 1
    product_paths = {f"/product/{quote(row['identity']['slug'], safe='')}/" for row in manifest["products"]}
    assert product_paths <= set(event["payload"]["paths"])
    assert "/brands/kinghome/" in event["payload"]["paths"]
    for id, product in after["products"].items():
        original = baseline["products"][id]
        for key in ("title", "slug", "brand_id", "series_id", "product_kind", "source_url", "price", "description", "main_image"):
            assert product[key] == original[key]
        for key in ("unrelated", "__filter_unrelated", "power_cons_cooling_kw", "type", "type_tags"):
            assert product["specs"][key] == original["specs"][key]
        assert product["specs"]["__typed_specs"]["unrelated"] == {"value": "exact"}
    assert after["products"][179]["price"] == 6789
    assert "380-415" in after["products"][179]["specs"]["power_supply_outdoor"]
    assert after["products"][1075]["product_kind"] == baseline["products"][1075]["product_kind"]
    for id in (520, 555, 558):
        assert after["products"][id]["specs"]["power_supply_voltage"] == "220-240"
        for key in ("power_supply", "power_supply_location"):
            assert after["products"][id]["specs"][key] == baseline["products"][id]["specs"][key]
            assert after["products"][id]["specs"]["__typed_specs"][key] == baseline["products"][id]["specs"]["__typed_specs"][key]

    # The old before-plan is stale after commit; only a fresh zero-change plan repeats.
    with pytest.raises(RepairBlocked, match="changed since review"):
        await run(execute=True, reviewed_plan=reviewed_path, execute_plan_digest=reviewed["plan_digest"])
    assert await snapshot(factory) == after
    noop = await run()
    assert noop["changed"] == 0
    reviewed_path.write_text(json.dumps(noop))
    result = await run(execute=True, reviewed_plan=reviewed_path, execute_plan_digest=noop["plan_digest"])
    assert result["changed"] == 0 and result["revision"] is None
    assert await snapshot(factory) == after
