"""Issue-1190 repair against a dedicated physical PostgreSQL test database."""

from copy import deepcopy
from decimal import Decimal
import json
import re

import pytest
import pytest_asyncio
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, sessionmaker
from sqlmodel import select

from crud.catalog_revision import CatalogRevisionDAO
from models import Brand, IntegrationOutboxEvent, Product, ProductSeries, Tag
from models.supplier import ProductLocalStock, ProductSupplierMapping, Supplier, SupplierOffer, SupplierPriceSource
from models.tenancy import TenantScope
from scripts.repair_catalog_decision_sources import run
from services.catalog_decision_data_repair import RepairBlocked, digest
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService
from services.catalog_decision_source_repair import SCOPE_IDS, SUPPLIER_KEYS, commerce_projection, product_projection
from services.catalog_revision_service import CatalogRevisionService
from tests.catalog_decision_source_repair_support import pin_fixture, prepared_catalog


def columns(obj):
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


async def database_state(factory):
    async with factory() as session:
        return deepcopy({
            "products": [p.model_dump(mode="json") for p in (await session.execute(select(Product).order_by(Product.id))).scalars()],
            "events": [e.model_dump(mode="json") for e in (await session.execute(select(IntegrationOutboxEvent).order_by(IntegrationOutboxEvent.event_id))).scalars()],
            "revision": (await CatalogRevisionDAO.get_current(session)).revision,
        })


@pytest_asyncio.fixture
async def catalog(db_engine, monkeypatch, tmp_path):
    assert db_engine.dialect.name == "postgresql" and re.search(r"(?:^|_)test(?:_|$)", db_engine.url.database)
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    import core.database
    monkeypatch.setattr(core.database, "async_session_maker", factory)
    manifest, source_products, _ = prepared_catalog()
    brands = {p.brand_id: Brand(id=p.brand_id, title=p.brand.slug, slug=p.brand.slug) for p in source_products}
    series = {p.series_id: ProductSeries(id=p.series_id, brand_id=p.brand_id, title=p.series.slug, slug=p.series.slug)
              for p in source_products if p.series_id is not None}
    async with factory() as session:
        session.add_all(brands.values())
        session.add(Supplier(id=2, name="Test supplier", code="test-source-1190", spreadsheet_id="test-sheet"))
        tag = Tag(title="Industrial", slug="cat-industrial")
        session.add(tag)
        await session.flush()
        session.add_all(series.values())
        await session.flush()
        for source in source_products:
            values = {k: v for k, v in vars(source).items() if k not in {"brand", "series", "tags"}}
            session.add(Product(**values, tags=[tag], main_image="keep.webp", description="Preserve content"))
        await session.flush()
        source = SupplierPriceSource(id=1190, supplier_id=2, sheet_name="Test kits", range_a1="A1:M100")
        session.add(source)
        await session.flush()
        offer = SupplierOffer(id=1190, supplier_id=2, source_id=1190, external_id="ZUB7-24HRIN4", qty=2,
                              wholesale_value=Decimal("1000.00"), wholesale_currency="BYN", rrc_byn=Decimal("1500.00"))
        session.add(offer)
        await session.flush()
        mapping = ProductSupplierMapping(id=1190, product_id=162, supplier_id=2, external_id=offer.external_id)
        session.add(mapping)
        await session.commit()
        supplier = await session.get(Supplier, 2)
        commerce = commerce_projection({"supplier_mappings": [{**columns(mapping), "supplier": {key: getattr(supplier, key) for key in SUPPLIER_KEYS}, "offer": columns(offer)}], "local_stocks": []}, [columns(source)])
        products = list((await session.execute(select(Product).order_by(Product.id).options(selectinload(Product.tags), selectinload(Product.brand), selectinload(Product.series)))).scalars())
        by_id = {p.id: p for p in products}
        for row in manifest["products"]:
            pid = row["identity"]["id"]
            row["before"] = product_projection(by_id[pid], commerce if pid == 162 else {"mappings": [], "sources": [], "local_stocks": []})
            row["before_sha256"] = digest(row["before"])
    pin_fixture(monkeypatch, manifest)
    path, reviewed = tmp_path / "manifest.json", tmp_path / "reviewed.json"
    path.write_text(json.dumps(manifest))
    return factory, manifest, path, reviewed


@pytest.mark.asyncio
async def test_readonly_manual_gate_atomic_rollback_success_strict_selection_and_noop(catalog, monkeypatch):
    factory, manifest, path, reviewed = catalog
    baseline = await database_state(factory)
    plan = await run(manifest_path=path)
    assert plan["changed"] == 149 and len(plan["blocked_items"]) == 68
    assert await database_state(factory) == baseline
    reviewed.write_text(json.dumps(plan))
    kwargs = dict(manifest_path=path, execute=True, reviewed_plan=reviewed, execute_plan_digest=plan["plan_digest"])
    with pytest.raises(RepairBlocked, match="Manual kind provenance"):
        await run(**kwargs)
    assert await database_state(factory) == baseline
    kwargs["manual_kind_review_digest"] = plan["plan_digest"]
    real_stage = CatalogRevisionService.stage_invalidation
    staged = []

    async def fail_after_real_stage(session, **values):
        result = await real_stage(session, **values)
        assert result["revision"] == 1
        assert len(list((await session.execute(select(IntegrationOutboxEvent))).scalars())) == 1
        assert (await session.get(Product, 162)).product_kind == "complete_split_system"
        staged.append(True)
        raise RuntimeError("after real revision/outbox staging")

    with monkeypatch.context() as failure:
        failure.setattr(CatalogRevisionService, "stage_invalidation", fail_after_real_stage)
        with pytest.raises(RuntimeError, match="after real revision/outbox"):
            await run(**kwargs)
    assert staged == [True] and await database_state(factory) == baseline
    result = await run(**kwargs)
    assert result["changed"] == 149 and result["revision"]["revision"] == 1
    after = await database_state(factory)
    assert len(after["events"]) == 1 and set(plan["series_paths"]) <= set(after["events"][0]["payload"]["paths"])
    for before, current in zip(baseline["products"], after["products"]):
        assert {key: value for key, value in before.items() if key != "product_kind"} == {key: value for key, value in current.items() if key != "product_kind"}
        assert current["product_kind"] == ("complete_split_system" if current["id"] in plan["product_ids"] else before["product_kind"])
    async with factory() as session:
        eligible = await CatalogDecisionQueryService.eligible_system_product_ids(session, sorted(SCOPE_IDS))
        assert eligible == set(plan["product_ids"])
        scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
        selection = await CatalogDecisionQueryService.list_products(session, tenant_scope=scope, filters=CatalogDecisionFilters(product_ids=tuple(SCOPE_IDS)), page=1, limit=100, sort="title", direction="asc")
        assert selection["meta"]["total"] == 149
        in_stock = await CatalogDecisionQueryService.list_products(session, tenant_scope=scope, filters=CatalogDecisionFilters(product_ids=tuple(SCOPE_IDS), availability="in_stock"), page=1, limit=100, sort="title", direction="asc")
        assert [p["id"] for p in in_stock["items"]] == [162]
        snapshots = await CatalogDecisionQueryService.get_product_snapshots(session, tenant_scope=scope, product_ids=sorted(SCOPE_IDS))
        assert snapshots.keys() == eligible
        with pytest.raises(ValueError, match="Unsupported cooling BTU"):
            await CatalogDecisionQueryService.list_products(session, tenant_scope=scope, filters=CatalogDecisionFilters(cooling_btu_classes=(48,)), page=1, limit=100, sort="title", direction="asc")
    with pytest.raises(RepairBlocked, match="changed since review"):
        await run(**kwargs)
    noop = await run(manifest_path=path)
    assert noop["changed"] == 0
    reviewed.write_text(json.dumps(noop))
    result = await run(manifest_path=path, execute=True, reviewed_plan=reviewed, execute_plan_digest=noop["plan_digest"])
    assert result["changed"] == 0 and result["revision"] is None
    assert await database_state(factory) == after


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["price", "qty", "mapping", "source", "supplier", "local_stock", "title", "specs"])
async def test_commercial_or_product_drift_blocks_execution_without_other_mutations(catalog, fault):
    factory, _, path, reviewed = catalog
    plan = await run(manifest_path=path)
    reviewed.write_text(json.dumps(plan))
    async with factory() as session:
        if fault in {"price", "qty"}:
            offer = await session.get(SupplierOffer, 1190)
            if fault == "price":
                offer.wholesale_value = Decimal("1001.00")
            else:
                offer.qty = 3
            session.add(offer)
        elif fault == "mapping":
            obj = await session.get(ProductSupplierMapping, 1190)
            obj.is_active = False
            session.add(obj)
        elif fault == "source":
            obj = await session.get(SupplierPriceSource, 1190)
            obj.range_a1 = "A101:M200"
            session.add(obj)
        elif fault == "supplier":
            obj = await session.get(Supplier, 2)
            obj.is_active = False
            session.add(obj)
        elif fault == "local_stock":
            session.add(ProductLocalStock(product_id=162, qty=1))
        else:
            obj = await session.get(Product, 162)
            if fault == "title":
                obj.title += " other"
            else:
                obj.specs = {**obj.specs, "includes_outdoor_unit": False}
            session.add(obj)
        await session.commit()
    before_attempt = await database_state(factory)
    with pytest.raises(RepairBlocked, match="changed"):
        await run(manifest_path=path, execute=True, reviewed_plan=reviewed, execute_plan_digest=plan["plan_digest"], manual_kind_review_digest=plan["plan_digest"])
    assert await database_state(factory) == before_attempt


@pytest.mark.asyncio
async def test_category_cannot_be_renamed_between_review_and_commit(catalog, monkeypatch):
    factory, _, path, reviewed = catalog
    plan = await run(manifest_path=path)
    reviewed.write_text(json.dumps(plan))
    real_stage = CatalogRevisionService.stage_invalidation
    blocked = []

    async def verify_category_lock(session, **values):
        async with factory() as concurrent:
            await concurrent.execute(text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(DBAPIError, match="lock timeout"):
                await concurrent.execute(update(Tag).where(Tag.slug == "cat-industrial").values(slug="cat-multi"))
            await concurrent.rollback()
            blocked.append(True)
        return await real_stage(session, **values)

    monkeypatch.setattr(CatalogRevisionService, "stage_invalidation", verify_category_lock)
    result = await run(manifest_path=path, execute=True, reviewed_plan=reviewed,
                       execute_plan_digest=plan["plan_digest"], manual_kind_review_digest=plan["plan_digest"])
    assert result["changed"] == 149 and blocked == [True]
    async with factory() as session:
        assert (await session.execute(select(Tag.slug))).scalars().all() == ["cat-industrial"]
