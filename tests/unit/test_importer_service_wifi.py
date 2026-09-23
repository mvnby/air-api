from services.spec_normalizer import normalize_specs
from services.tag_logic import get_auto_tags


def test_wifi_specs_do_not_create_technical_product_tags():
    for value, expected in (("да", "builtin"), ("приобретается отдельно", "ready")):
        specs = normalize_specs({"Wi-Fi модуль": value})
        slugs = get_auto_tags({}, specs=specs, title="MDV тест")

        assert specs["wifi_state"] == expected
        assert "wifi-builtin" not in slugs
        assert "wifi-ready" not in slugs
