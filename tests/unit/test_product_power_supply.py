import json
from pathlib import Path

import pytest

from services.product_power_supply import build_product_power_supply_description
from services.spec_normalizer import normalize_specs

CASES = json.loads(Path("tests/fixtures/product_power_supply.json").read_text())
REPAIR_ROWS = json.loads(Path("config/catalog_source_repairs/power-supply-2026-10.json").read_text())["products"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_known_power_supply_description(case):
    assert build_product_power_supply_description(case["specs"], case.get("product_kind")) == case["expected"]


def test_tcl195_fixture_uses_exact_reviewed_manifest_specs():
    fixture = next(case for case in CASES if case["name"] == "reviewed TCL195 block aggregate")
    row = next(row for row in REPAIR_ROWS if row["identity"]["id"] == 195)
    assert fixture["specs"] == row["specs_set"]


@pytest.mark.parametrize("row", REPAIR_ROWS, ids=lambda row: str(row["identity"]["id"]))
def test_reviewed_repair_rows_have_no_unresolved_power_warning(row):
    result = build_product_power_supply_description(row["specs_set"], row["identity"]["product_kind"])
    assert " В" in result
    assert "уточн" not in result


@pytest.mark.parametrize("key,canonical", [
    ("Электропитание, В/Гц/Ф", "power_supply"),
    ("Электропитание внутреннего блока В/Гц/Ф", "power_supply_indoor"),
    ("Электропитание внутреннего блока, В/Гц/Ф", "power_supply_indoor"),
    ("Электропитание наружного блока В/Гц/Ф", "power_supply_outdoor"),
    ("Электропитание наружного блока, В/Гц/Ф", "power_supply_outdoor"),
])
def test_power_supply_legacy_aliases_use_registry(key, canonical):
    assert normalize_specs({key: "380-415/50/3"})[canonical] == "380-415/50/3"
