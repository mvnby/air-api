import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.backfill_product_area_m2 import _model_matches_product
from services.catalog_area_backfill import (
    CatalogAreaPlanError,
    build_specs_update,
    load_plan_entries,
    should_apply,
)


def _entry(**overrides):
    payload = {
        "product_id": 10,
        "model": "AS-12TEST",
        "proposed_area_m2": 35,
        "source": "official source",
        "confidence": "high",
        "explanation": "Manufacturer states up to 35 m2.",
        "status": "candidate",
    }
    payload.update(overrides)
    return load_plan_entries({"entries": [payload]})[0]


def test_backfill_adds_only_missing_canonical_area():
    assert build_specs_update({"brand": "Hisense"}, _entry()) == {
        "brand": "Hisense",
        "area_m2": "35",
    }
    assert build_specs_update({"area_m2": "27"}, _entry()) is None


def test_backfill_respects_confidence_threshold():
    assert should_apply(_entry(confidence="high"), "high") is True
    assert should_apply(_entry(confidence="medium"), "high") is False
    assert should_apply(_entry(confidence="medium"), "medium") is True


def test_non_candidate_does_not_get_an_area():
    entry = _entry(status="not_applicable", proposed_area_m2=None)
    assert build_specs_update({}, entry) is None


def test_plan_rejects_duplicate_ids_and_missing_candidate_area():
    with pytest.raises(CatalogAreaPlanError, match="unique"):
        load_plan_entries({"entries": [_entry().__dict__, _entry().__dict__]})
    with pytest.raises(CatalogAreaPlanError, match="positive integer area"):
        load_plan_entries({"entries": [{**_entry().__dict__, "proposed_area_m2": None}]})


def test_backfill_requires_the_reviewed_model_to_match_the_product_title():
    entry = _entry(model="AS-12TEST")
    assert _model_matches_product(SimpleNamespace(title="Hisense AS-12TEST комплект"), entry)
    assert not _model_matches_product(SimpleNamespace(title="Hisense AS-18OTHER комплект"), entry)


def test_reviewed_plan_covers_the_production_snapshot_without_low_confidence_writes():
    plan_path = Path(__file__).parents[2] / "data" / "catalog_area_backfill_plan_2026-07-19.json"
    entries = load_plan_entries(json.loads(plan_path.read_text(encoding="utf-8")))

    assert len(entries) == 66
    assert sum(entry.status == "candidate" for entry in entries) == 64
    assert sum(entry.status == "not_applicable" for entry in entries) == 2
    assert not [entry for entry in entries if entry.confidence == "low"]
