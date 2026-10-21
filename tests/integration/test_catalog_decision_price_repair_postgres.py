"""Approved price-first deltas commit atomically in an isolated PostgreSQL DB."""

from copy import deepcopy
import json
from types import SimpleNamespace as NS

import pytest
import pytest_asyncio
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import IntegrationOutboxEvent, Product
from models.tenancy import TenantScope
from scripts.repair_catalog_decision_prices import run
from services.catalog_decision_data_repair import RepairBlocked, digest
from services.catalog_decision_price_repair import SCOPE_IDS, apply_operation, load_manifest
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService
from services.catalog_decision_source_repair import PRODUCT_STATE_KEYS, product_identity, product_projection
from services.catalog_revision_service import CatalogRevisionService
from tests.catalog_decision_price_repair_support import pin_fixture, reset_technical_before
from tests.integration.test_catalog_decision_source_repair_postgres import catalog as base_catalog, database_state  # noqa: F401


@pytest_asyncio.fixture
async def catalog(base_catalog, monkeypatch):
    factory, original, path, reviewed = base_catalog
    manifest = deepcopy(load_manifest())
    old_rows = {r["identity"]["id"]: r for r in original["products"]}
    async with factory() as session:
        products = list((await session.execute(select(Product).options(
            selectinload(Product.tags), selectinload(Product.brand), selectinload(Product.series)))).scalars())
        by_id = {p.id: p for p in products}
        for row in manifest["products"]:
            product = by_id[row["identity"]["id"]]
            reset_technical_before(product, row)
            session.add(product)
            row["identity"] = product_identity(product)
            before = product_projection(product, {})
            before["commerce_sha256"] = old_rows[product.id]["before"]["commerce_sha256"]
            row["before"] = before
            target = NS(**{key: getattr(product, key) for key in (*PRODUCT_STATE_KEYS, "id", "price", "old_price", "tags", "brand", "series")}, specs=deepcopy(product.specs))
            apply_operation(target, row)
            row["target"] = product_projection(target, {})
            row["target"]["commerce_sha256"] = before["commerce_sha256"]
            row["before_sha256"], row["target_sha256"] = digest(before), digest(row["target"])
        await session.commit()
    pin_fixture(monkeypatch, manifest)
    path.write_text(json.dumps(manifest))
    return factory, manifest, path, reviewed


@pytest.mark.asyncio
async def test_readonly_manual_gate_rollback_exact_changes_strict_selection_and_noop(catalog, monkeypatch):
    factory, manifest, path, reviewed = catalog
    baseline = await database_state(factory)
    plan = await run(manifest_path=path)
    assert plan["changed"] == 167 and plan["technical_changes"] == {"products": 67, "fields": 319}
    assert await database_state(factory) == baseline
    reviewed.write_text(json.dumps(plan))
    kwargs = dict(manifest_path=path, execute=True, reviewed_plan=reviewed, execute_plan_digest=plan["plan_digest"])
    with pytest.raises(RepairBlocked, match="Manual kind provenance"):
        await run(**kwargs)
    kwargs["manual_kind_review_digest"] = plan["plan_digest"]
    real_stage = CatalogRevisionService.stage_invalidation

    async def fail_after_staging(session, **values):
        await real_stage(session, **values)
        assert len(list((await session.execute(select(IntegrationOutboxEvent))).scalars())) == 1
        assert (await session.get(Product, 161)).specs["model_outdoor"] == "ZOD-60HRIN4S"
        raise RuntimeError("rollback all fields with staged revision and outbox")

    with monkeypatch.context() as failure:
        failure.setattr(CatalogRevisionService, "stage_invalidation", fail_after_staging)
        with pytest.raises(RuntimeError, match="rollback all fields"):
            await run(**kwargs)
    assert await database_state(factory) == baseline
    result = await run(**kwargs)
    assert result["changed"] == 167 and result["revision"]["revision"] == 1
    assert result["technical_changes"] == {"products": 67, "fields": 319}
    after = await database_state(factory)
    assert len(after["events"]) == 1 and set(plan["series_paths"]) <= set(after["events"][0]["payload"]["paths"])
    rows = {r["identity"]["id"]: r for r in manifest["products"]}
    for old, new in zip(baseline["products"], after["products"]):
        expected = NS(product_kind=old["product_kind"], specs=deepcopy(old["specs"]), power_cooling=old["power_cooling"])
        apply_operation(expected, rows[old["id"]])
        assert new == {**old, **vars(expected)}  # All other model columns survive.
    async with factory() as session:
        eligible = await CatalogDecisionQueryService.eligible_system_product_ids(session, sorted(SCOPE_IDS))
        assert eligible == set(plan["product_ids"])
        scope = TenantScope(tenant_id=1, storefront_id=1, is_system=True)
        filters = CatalogDecisionFilters(product_ids=tuple(SCOPE_IDS))
        first = await CatalogDecisionQueryService.list_products(session, tenant_scope=scope, filters=filters, page=1, limit=100, sort="title", direction="asc")
        second = await CatalogDecisionQueryService.list_products(session, tenant_scope=scope, filters=filters, page=2, limit=100, sort="title", direction="asc")
        assert first["meta"]["total"] == second["meta"]["total"] == 167
        assert {p["id"] for p in first["items"] + second["items"]} == eligible
        snapshots = await CatalogDecisionQueryService.get_product_snapshots(session, tenant_scope=scope, product_ids=sorted(SCOPE_IDS))
        assert snapshots.keys() == eligible
        displayed = {item["id"]: item for item in first["items"] + second["items"]}
        for pid in [556, 559, 924, 949, 951, 1212]:
            expected_kw = next(p["after"] for p in rows[pid]["patches"] if p["path"] == "power_cooling")
            assert snapshots[pid].product.power_cooling == displayed[pid]["cooling_power_kw"] == expected_kw
        in_stock = await CatalogDecisionQueryService.list_products(session, tenant_scope=scope, filters=CatalogDecisionFilters(product_ids=tuple(SCOPE_IDS), availability="in_stock"), page=1, limit=100, sort="title", direction="asc")
        assert [p["id"] for p in in_stock["items"]] == [162]
    with pytest.raises(RepairBlocked, match="changed since review"):
        await run(**kwargs)
    noop = await run(manifest_path=path)
    assert noop["changed"] == 0 and noop["technical_changes"] == {"products": 0, "fields": 0}
    reviewed.write_text(json.dumps(noop))
    result = await run(manifest_path=path, execute=True, reviewed_plan=reviewed, execute_plan_digest=noop["plan_digest"])
    assert result["revision"] is None and await database_state(factory) == after


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["unrelated_spec", "typed_spec", "power", "held", "partial"])
async def test_stale_or_partially_applied_fields_abort_without_extra_writes(catalog, fault):
    factory, manifest, path, reviewed = catalog
    plan = await run(manifest_path=path)
    reviewed.write_text(json.dumps(plan))
    async with factory() as session:
        p = await session.get(Product, 191 if fault == "held" else 161)
        if fault == "unrelated_spec":
            p.specs = {**p.specs, "manual_note": "preserve"}
        elif fault == "typed_spec":
            p.specs = {**p.specs, "__typed_specs": {**p.specs.get("__typed_specs", {}), "model_outdoor": {"value": "different"}}}
        elif fault in {"power", "held"}:
            p.power_cooling = 100
        else:
            apply_operation(p, next(r for r in manifest["products"] if r["identity"]["id"] == 161))
        session.add(p)
        await session.commit()
    before_attempt = await database_state(factory)
    with pytest.raises(RepairBlocked, match="changed|Partial"):
        await run(manifest_path=path, execute=True, reviewed_plan=reviewed, execute_plan_digest=plan["plan_digest"], manual_kind_review_digest=plan["plan_digest"])
    assert await database_state(factory) == before_attempt
