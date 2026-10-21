"""Exact CLI repair against a dedicated physical PostgreSQL test database."""

from copy import deepcopy
import json
import re

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.catalog_revision import CatalogRevisionDAO
from models import Brand, Product, ProductSeries, IntegrationOutboxEvent
from scripts.repair_catalog_decision_data import run
from services.catalog_decision_data_repair import KIND_IDS, POWER_TARGETS, digest, load_manifest, RepairBlocked
from services.catalog_revision_service import CatalogRevisionService


async def snapshot(factory):
    async with factory() as session:
        products = [obj.model_dump(mode="json") for obj in (await session.execute(select(Product).order_by(Product.id))).scalars()]
        events = [obj.model_dump(mode="json") for obj in (await session.execute(select(IntegrationOutboxEvent).order_by(IntegrationOutboxEvent.event_id))).scalars()]
        return deepcopy({"products": products, "events": events, "revision": (await CatalogRevisionDAO.get_current(session)).revision})


@pytest.mark.asyncio
async def test_cli_readonly_manual_review_rollback_atomic_success_and_noop(db_engine, monkeypatch, tmp_path):
    assert db_engine.dialect.name == "postgresql"
    assert re.search(r"(?:^|_)test(?:_|$)", db_engine.url.database)
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    import core.database
    monkeypatch.setattr(core.database, "async_session_maker", factory)
    manifest = deepcopy(load_manifest())
    brands = [Brand(id=3, title="TCL", slug="tcl"), Brand(id=4, title="KINGHOME", slug="kinghome")]
    series = [ProductSeries(id=9003, brand_id=3, title="TCL source", slug="tcl-source"), ProductSeries(id=9004, brand_id=4, title="KingHome source", slug="kinghome-source")]
    products = []
    for row in manifest["products"]:
        identity = row["identity"]
        pid = identity["id"]
        identity["series_id"] = 9004 if pid in KIND_IDS else 9003
        target = POWER_TARGETS.get(pid, 10.55)
        specs = {"type": "полупромышленный кондиционер", "capacity_cooling_kw": str(target), "untouched": {"exact": [1, 2]}}
        if pid in KIND_IDS:
            specs.update(includes_indoor_unit=True, includes_outdoor_unit="true", indoor_units_count="1")
        row["before"]["tag_slugs"] = []
        row["before"]["specs_sha256"] = digest(specs)
        row["before_sha256"] = digest(row["before"])
        products.append(Product(**identity, product_kind=row["before"]["product_kind"], power_cooling=row["before"]["power_cooling"], specs=specs, price=3456, main_image="https://example.invalid/keep.webp", description="Keep description"))
    async with factory() as session:
        session.add_all(brands)
        await session.flush()
        session.add_all(series)
        await session.flush()
        session.add_all(products)
        await session.commit()
    path, reviewed_path = tmp_path / "manifest.json", tmp_path / "reviewed.json"
    path.write_text(json.dumps(manifest))
    baseline = await snapshot(factory)
    plan = await run(manifest_path=path)
    assert plan["changed"] == 34 and await snapshot(factory) == baseline
    reviewed_path.write_text(json.dumps(plan))
    kwargs = dict(manifest_path=path, execute=True, reviewed_plan=reviewed_path, execute_plan_digest=plan["plan_digest"])
    with pytest.raises(RepairBlocked, match="Manual kind provenance"):
        await run(**kwargs)
    assert await snapshot(factory) == baseline
    kwargs["manual_kind_review_digest"] = plan["plan_digest"]
    real_staging = CatalogRevisionService.stage_invalidation
    staged = []

    async def fail_after_real_staging(session, **values):
        result = await real_staging(session, **values)
        assert result["revision"] == 1
        assert len(list((await session.execute(select(IntegrationOutboxEvent))).scalars())) == 1
        assert (await session.get(Product, 180)).power_cooling == 16.12
        assert (await session.get(Product, 94)).product_kind == "complete_split_system"
        staged.append(True)
        raise RuntimeError("after real revision/outbox staging")

    with monkeypatch.context() as failure:
        failure.setattr(CatalogRevisionService, "stage_invalidation", fail_after_real_staging)
        with pytest.raises(RuntimeError, match="after real revision/outbox staging"):
            await run(**kwargs)
    assert staged == [True] and await snapshot(factory) == baseline
    result = await run(**kwargs)
    assert result["changed"] == 34 and result["revision"]["revision"] == 1
    after = await snapshot(factory)
    assert len(after["events"]) == 1
    paths = after["events"][0]["payload"]["paths"]
    assert set(plan["series_paths"]) <= set(paths)
    for before, product in zip(baseline["products"], after["products"]):
        for key in ("specs", "price", "main_image", "description", "source_url", "title", "slug"):
            assert product[key] == before[key]
        pid = product["id"]
        if pid in KIND_IDS:
            assert product["product_kind"] == "complete_split_system"
            assert product["power_cooling"] == before["power_cooling"]
        elif pid in POWER_TARGETS:
            assert product["power_cooling"] == POWER_TARGETS[pid]
            assert product["product_kind"] == before["product_kind"]
        else:
            assert product == before
    with pytest.raises(RepairBlocked, match="changed since review"):
        await run(**kwargs)
    noop = await run(manifest_path=path)
    assert noop["changed"] == 0
    reviewed_path.write_text(json.dumps(noop))
    repeated = await run(manifest_path=path, execute=True, reviewed_plan=reviewed_path, execute_plan_digest=noop["plan_digest"])
    assert repeated["changed"] == 0 and repeated["revision"] is None
    assert await snapshot(factory) == after
