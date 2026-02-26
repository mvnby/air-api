from services.importer_service import _augment_auto_slugs_with_wifi_specs


def test_importer_adds_wifi_builtin_slug_from_specs():
    slugs = _augment_auto_slugs_with_wifi_specs([], {"Wi-Fi": "да"})
    assert "wifi-builtin" in slugs
    assert "wifi-ready" not in slugs


def test_importer_adds_wifi_ready_slug_from_specs():
    slugs = _augment_auto_slugs_with_wifi_specs([], {"Wi-Fi модуль": "приобретается отдельно"})
    assert "wifi-ready" in slugs
    assert "wifi-builtin" not in slugs


def test_importer_does_not_duplicate_wifi_slug():
    slugs = _augment_auto_slugs_with_wifi_specs(["wifi-builtin"], {"Wi-Fi": "да"})
    assert slugs.count("wifi-builtin") == 1
