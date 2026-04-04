from types import SimpleNamespace

from services.brand_series_service import extract_series_name


def test_extract_series_name_from_specs():
    name = extract_series_name({"series": "Loft, Inverter"})
    assert name == "Loft"


def test_extract_series_name_from_russian_key():
    name = extract_series_name({"Серия": "BreezeIN 2.0"})
    assert name == "BreezeIN 2.0"


def test_extract_series_name_from_series_tag_fallback():
    tag = SimpleNamespace(
        title="Elite",
        group=SimpleNamespace(slug="series"),
    )
    name = extract_series_name({}, [tag])
    assert name == "Elite"
