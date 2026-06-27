from services.spec_normalizer import KEY_MAP, _DIMENSIONS_MAP
from services.spec_registry import (
    REGISTRY_DIMENSIONS_MAP,
    REGISTRY_KEY_MAP,
    REGISTRY_UNORDERED_DIMENSION_KEYS,
    SPEC_DEFINITIONS,
    get_specs_registry_payload,
)
from services.product_serialization import sanitize_specs


def test_registry_covers_all_normalized_spec_keys():
    canonical_keys = set(KEY_MAP.values())
    for dimensions_keys in _DIMENSIONS_MAP.values():
        canonical_keys.update(dimensions_keys)

    missing = sorted(key for key in canonical_keys if key not in SPEC_DEFINITIONS)

    assert missing == []


def test_normalizer_alias_map_is_registry_projection():
    assert KEY_MAP == REGISTRY_KEY_MAP


def test_normalizer_dimension_map_is_registry_projection():
    from services.spec_normalizer import _UNORDERED_WIDTH_HEIGHT_DIMENSION_KEYS

    assert _DIMENSIONS_MAP == REGISTRY_DIMENSIONS_MAP
    assert _UNORDERED_WIDTH_HEIGHT_DIMENSION_KEYS == set(REGISTRY_UNORDERED_DIMENSION_KEYS)


def test_specs_registry_payload_exposes_typed_metadata():
    payload = get_specs_registry_payload()

    assert payload["total"] == len(payload["items"])
    by_key = {item["key"]: item for item in payload["items"]}

    cooling = by_key["capacity_cooling_kw"]
    assert cooling["value_type"] == "quantity"
    assert cooling["quantity_kind"] == "power"
    assert cooling["canonical_unit"] == "kW"
    assert cooling["description"]

    inverter = by_key["inverter"]
    assert inverter["value_type"] == "boolean"

    weight = by_key["weight_indoor"]
    assert weight["value_type"] == "quantity"
    assert weight["quantity_kind"] == "weight"
    assert weight["canonical_unit"] == "kg"

    pipe = by_key["pipe_gas"]
    assert pipe["value_type"] == "enum"
    assert '5/8"' in pipe["enum_values"]


def test_specs_registry_payload_includes_legacy_aliases():
    payload = get_specs_registry_payload()
    by_key = {item["key"]: item for item in payload["items"]}

    assert "Мощность охлаждения" in by_key["capacity_cooling_kw"]["aliases"]
    assert "Потребление электроэнергии в режиме охлаждения (Мин / Ном / Макс), кВт" in by_key[
        "power_cons_cooling_kw"
    ]["aliases"]
    assert "Wi-Fi модуль" in by_key["wifi_ready"]["aliases"]
    assert "Габаритные размеры в упаковке (Ш/Г/В), мм" in by_key["dimensions_outdoor_package_mm"]["aliases"]


def test_specs_registry_payload_has_help_for_core_public_specs():
    payload = get_specs_registry_payload()
    by_key = {item["key"]: item for item in payload["items"]}
    core_keys = {
        "capacity_cooling_kw",
        "capacity_heating_kw",
        "power_cons_cooling_kw",
        "power_cons_heating_kw",
        "area_m2",
        "temp_range_heat",
        "airflow_max",
        "noise_indoor",
        "energy_class_cooling",
        "eer",
        "cop",
        "pipe_max_length",
        "pipe_gas",
        "freon_type",
        "refrigerant_charge_g",
        "width_indoor",
        "weight_outdoor",
        "warranty_months",
    }

    missing = sorted(key for key in core_keys if not by_key[key]["description"])

    assert missing == []


def test_specs_registry_payload_has_descriptions_for_all_specs():
    payload = get_specs_registry_payload()

    missing = sorted(item["key"] for item in payload["items"] if not item["description"])

    assert missing == []


def test_typed_specs_are_internal_serialization_details():
    specs = sanitize_specs({"capacity_cooling_kw": "2.5", "__typed_specs": {"capacity_cooling_kw": {"value": 2.5}}})

    assert specs == {"capacity_cooling_kw": "2.5"}
