from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.catalog_kinghome_source_repair import (
    RepairBlocked, build_plan, digest, load_manifest, repaired_specs,
    validate_manifest, validate_reviewed_plan,
)
from services.spec_normalizer import normalize_specs
from services.spec_registry import build_typed_specs


NOW = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(("raw", "values"), [
    ("1 000 куб. м/ч", [1000]),
    ("1\u00a0050 м³/ч", [1050]),
    ("2\u202f300 м³/ч", [2300]),
    ("1 000 / 1 250 / 900 м³/ч", [1000, 1250, 900]),
    ("1 000–1 250 м³/ч", [1000, 1250]),
    ("-1 000 м³/ч", [-1000]),
    ("1 000,5 м³/ч", [1000.5]),
    ("12,5 / 15.5 куб. м/ч", [12.5, 15.5]),
    ("500 / 700 м³/ч", [500, 700]),
])
def test_airflow_grouping_preserves_ranges_lists_signs_and_decimals(raw, values):
    direct = build_typed_specs({"airflow_max": raw})["airflow_max"]
    normalized = normalize_specs({"airflow_max": raw})["__typed_specs"]["airflow_max"]
    assert direct["values"] == normalized["values"] == values
    assert direct["max"] == max(values)
    assert direct["raw"] == raw


def test_grouping_change_is_limited_to_airflow():
    typed = build_typed_specs({"noise_indoor": "1 000 дБ", "airflow_max": "1 000 куб. м/ч"})
    assert typed["noise_indoor"]["values"] == [1, 0]
    assert typed["airflow_max"]["values"] == [1000]


@pytest.fixture
def catalog():
    manifest = deepcopy(load_manifest())
    products, series = [], []
    for row in manifest["products"]:
        before = row["before"]
        specs = {key: cell["value"] for section in ("specs", "filters") for key, cell in before[section].items() if cell["present"]}
        specs["__typed_specs"] = {key: cell["value"] for key, cell in before["typed"].items() if cell["present"]}
        specs.update({"unrelated": {"keep": [1, 2]}, "__filter_unrelated": 91})
        specs["__typed_specs"]["unrelated"] = {"keep": "exactly"}
        description = f"Original product {row['identity']['id']}"
        for key in before["fields_sha256"]:
            before["fields_sha256"][key] = digest(description)
        row["source_before_sha256"] = digest(before)
        products.append(SimpleNamespace(**row["identity"], specs=specs, description=description, price="not-in-plan", product_kind="other"))
    for row in manifest["series"]:
        values = {"description": f"Original series {row['identity']['id']}", "short_description": "Original short text", "content_blocks": [], "feature_blocks": []}
        row["before_sha256"] = {key: digest(values[key]) for key in row["before_sha256"]}
        series.append(SimpleNamespace(**row["identity"], **values, seo_title="keep SEO", gallery_images=["keep.webp"]))
    return manifest, products, series, SimpleNamespace(**manifest["brand"])


def apply_fixture(manifest, products, series):
    for row, obj in zip(manifest["products"], products):
        obj.specs = repaired_specs(obj.specs, row)
        for key, value in row["fields_set"].items():
            setattr(obj, key, value)
    for row, obj in zip(manifest["series"], series):
        for key, value in row["fields_set"].items():
            setattr(obj, key, value)


def test_plan_applies_exact_frozen_scope_and_becomes_noop(catalog):
    manifest, products, series, brand = catalog
    before = deepcopy(products)
    plan = build_plan(*catalog, now=NOW)
    assert plan["changed"] == 43  # 36 products and seven series in one transaction.
    assert len(plan["product_ids"]) == 42
    assert len(plan["series_paths"]) == 9
    assert "/brands/kinghome/series/cosmo-nordic/" in plan["series_paths"]
    assert "not-in-plan" not in json.dumps(plan)
    apply_fixture(manifest, products, series)
    assert build_plan(*catalog, now=NOW)["changed"] == 0
    for old, obj in zip(before, products):
        assert obj.specs["unrelated"] == old.specs["unrelated"]
        assert obj.specs["__typed_specs"]["unrelated"] == old.specs["__typed_specs"]["unrelated"]
        assert obj.specs["__filter_unrelated"] == old.specs["__filter_unrelated"]
        assert obj.price == old.price and obj.product_kind == old.product_kind
    assert all(obj.seo_title == "keep SEO" and obj.gallery_images == ["keep.webp"] for obj in series)


def test_only_selected_families_are_rebuilt(catalog, monkeypatch):
    manifest, products, _, _ = catalog
    from services import catalog_kinghome_source_repair as repair
    original = repair.normalize_specs
    calls = []
    monkeypatch.setattr(repair, "normalize_specs", lambda value: (calls.append(value), original(value))[1])
    apply_fixture(*catalog[:3])
    assert all(value == {"wifi_ready": "ready"} for value in calls)
    by_id = {p.id: p for p in products}
    assert by_id[1301].specs["__filter_noise_min"] == 34
    assert by_id[1301].specs["__typed_specs"]["airflow_max"]["max"] == 1100
    assert by_id[766].specs["__typed_specs"]["temp_range_heat"]["max"] == 24
    assert by_id[766].specs["__filter_min_heat"] == -30
    assert by_id[761].specs["self_cleaning"] is True
    assert by_id[1309].specs["width_indoor"] == "1400"
    assert by_id[1309].specs["height_indoor"] == "300"
    assert by_id[1309].specs["depth_indoor"] == "700"
    for id, height in [(1301, "200"), (1304, "290")]:
        assert by_id[id].specs["height_indoor"] == height
        assert by_id[id].specs["__typed_specs"]["height_indoor"]["value"] == int(height)
        assert by_id[id].specs["width_indoor"] == by_id[id].specs["depth_indoor"] == "840"
    for id in (764, 768, 769, 770):
        assert "ionizer" not in by_id[id].specs
        assert "ionizer" not in by_id[id].specs["__typed_specs"]
    for p in products:
        if p.series_id in (231, 232, 233):
            assert p.specs["wifi_ready"] == p.specs["wifi_state"] == "ready"
            assert p.specs["wifi_builtin"] is False
            assert p.specs["__typed_specs"]["wifi_ready"]["value"] == "ready"
            assert p.specs["__filter_wifi"] is True
            assert p.specs["__filter_wifi_builtin"] is False


@pytest.mark.parametrize("fault", ["missing", "extra", "title", "brand", "series", "source", "partial", "typed", "description"])
def test_planner_blocks_missing_changed_unknown_or_partial_state(catalog, fault):
    manifest, products, series, brand = catalog
    if fault == "missing":
        products.pop()
    elif fault == "extra":
        products.append(SimpleNamespace(id=99999))
    elif fault in {"title", "brand", "series"}:
        setattr(products[0], {"title": "title", "brand": "brand_id", "series": "series_id"}[fault], "unexpected")
    elif fault == "source":
        products[0].specs["noise_indoor"] = "new unreviewed value"
    elif fault == "partial":
        products[0].specs = repaired_specs(products[0].specs, manifest["products"][0])
        products[0].description = manifest["products"][0]["fields_set"]["description"]
    elif fault == "typed":
        products[0].specs["__typed_specs"]["airflow_max"] = {"value": 999}
    else:
        products[0].description = "unreviewed edit"
    with pytest.raises(RepairBlocked):
        build_plan(manifest, products, series, brand, now=NOW)


def test_identity_guards_still_apply_to_completed_and_unchanged_rows(catalog):
    apply_fixture(*catalog[:3])
    unchanged = next(p for p in catalog[1] if p.id == 172)
    unchanged.title = "different model"
    with pytest.raises(RepairBlocked, match="Identity"):
        build_plan(*catalog, now=NOW)


@pytest.mark.parametrize("fault", ["source_hash", "source_sheet", "price", "dimensions", "missing_guard"])
def test_manifest_rejects_scope_expansion_or_missing_guards(catalog, fault):
    m = catalog[0]
    if fault == "source_hash":
        m["sources"]["catalog_sha256"] = "0" * 64
    elif fault == "source_sheet":
        m["sources"]["supplier_sheet_url"] = "https://example.com"
    elif fault == "price":
        m["products"][0]["fields_set"]["price"] = "1"
    elif fault == "dimensions":
        m["products"][0]["specs_set"]["height_indoor"] = "665"
    else:
        m["products"][0]["before"]["typed"].pop("airflow_max")
        m["products"][0]["source_before_sha256"] = digest(m["products"][0]["before"])
    with pytest.raises(RepairBlocked):
        validate_manifest(m)


@pytest.mark.parametrize(("id", "key", "value"), [
    (1301, "height_indoor", "210"),
    (1304, "height_indoor", "200"),
    (1301, "depth_indoor", "200"),
    (1304, "width_indoor", "840"),
])
def test_confirmed_cassette_heights_do_not_authorize_other_dimension_edits(catalog, id, key, value):
    row = next(row for row in catalog[0]["products"] if row["identity"]["id"] == id)
    row["specs_set"][key] = value
    row["rebuild_typed"] = sorted(set(row["rebuild_typed"]) | {key})
    with pytest.raises(RepairBlocked, match="exact user-confirmed dimensions"):
        validate_manifest(catalog[0])


def test_review_requires_exact_digest_fresh_window_manifest_and_live_state(catalog):
    reviewed = build_plan(*catalog, now=NOW)
    live = build_plan(*catalog, now=NOW + timedelta(minutes=1))
    validate_reviewed_plan(reviewed, live, reviewed["plan_digest"], now=NOW + timedelta(minutes=1))
    with pytest.raises(RepairBlocked, match="expired"):
        validate_reviewed_plan(reviewed, live, reviewed["plan_digest"], now=NOW + timedelta(minutes=30))
    with pytest.raises(RepairBlocked, match="digest"):
        validate_reviewed_plan(reviewed, live, "0" * 64, now=NOW)
    live["manifest_sha256"] = "0" * 64
    with pytest.raises(RepairBlocked, match="changed"):
        validate_reviewed_plan(reviewed, live, reviewed["plan_digest"], now=NOW)
    live["manifest_sha256"] = reviewed["manifest_sha256"]
    live["state_digest"] = "0" * 64
    with pytest.raises(RepairBlocked, match="changed"):
        validate_reviewed_plan(reviewed, live, reviewed["plan_digest"], now=NOW)


def test_execute_rejects_replica_and_unknown_primary_without_loading_runtime():
    from scripts.repair_kinghome_catalog import require_primary
    require_primary(False, True)
    require_primary(True, False)
    for recovery in (True, None, "false", 0):
        with pytest.raises(RepairBlocked, match="primary"):
            require_primary(True, recovery)


def test_fixture_database_gate_rejects_production_names_and_isolates_workers():
    from postgres_test_support import build_test_database_target
    with pytest.raises(ValueError, match="non-test database"):
        build_test_database_target("postgresql+asyncpg://local:test@localhost/catalog", run_id="kinghome", worker_id="gw0")
    base = "postgresql+asyncpg://local:local@localhost/catalog_test"
    first = build_test_database_target(base, run_id="kinghome", worker_id="gw0")
    second = build_test_database_target(base, run_id="kinghome", worker_id="gw1")
    assert first.database_name != second.database_name
    assert first.database_name != "catalog_test"


@pytest.mark.asyncio
async def test_series_paths_share_one_atomic_commit_boundary(monkeypatch):
    from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService
    from services.catalog_revision_service import CatalogRevisionService
    session = AsyncMock()
    stage = AsyncMock(return_value={"revision": 1542})
    monkeypatch.setattr(CatalogRevisionService, "stage_invalidation", stage)
    paths = ["/brands/kinghome/series/cosmo/"]
    result = await CatalogInvalidationCommitService.commit_global_mutation(session, reason="kinghome_source_catalog_repair", product_ids=list(range(42)), brand_slugs=["kinghome"], additional_paths=paths)
    stage.assert_awaited_once()
    assert stage.await_args.kwargs["additional_paths"] == paths
    session.commit.assert_awaited_once_with()
    assert result == {"revision": 1542}
