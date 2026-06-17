import pytest

from services.address_suggest_service import AddressSuggestService


@pytest.mark.asyncio
async def test_suggest_prefers_vitebsk_region_then_falls_back(monkeypatch):
    calls: list[str] = []

    async def fake_fetch_raw(query: str, *, bbox: str | None = None, ull: str | None = None, strict_bounds: bool = True):
        assert query == "Ленина 1"
        assert strict_bounds is True
        assert ull is None
        calls.append(bbox or "")
        if bbox == AddressSuggestService.VITEBSK_REGION_BBOX:
            return {
                "results": [
                    {
                        "title": {"text": "улица Ленина, 1"},
                        "subtitle": {"text": "Витебск"},
                    }
                ]
            }
        return {
            "results": [
                {
                    "title": {"text": "улица Ленина, 1"},
                    "subtitle": {"text": "Витебск"},
                },
                {
                    "title": {"text": "улица Ленина, 1"},
                    "subtitle": {"text": "Минск"},
                },
            ]
        }

    monkeypatch.setattr(AddressSuggestService, "fetch_raw", fake_fetch_raw)

    items = await AddressSuggestService.suggest("Ленина 1")

    assert calls == [
        AddressSuggestService.VITEBSK_REGION_BBOX,
        AddressSuggestService.BELARUS_BBOX,
    ]
    assert [item["value"] for item in items] == [
        "Витебск, улица Ленина, д. 1",
        "Минск, улица Ленина, д. 1",
    ]


def test_normalize_results_deduplicates_and_skips_invalid_entries():
    payload = {
        "results": [
            {
                "title": {"text": "улица Ленина, 1"},
                "subtitle": {"text": "Витебск"},
            },
            {
                "title": {"text": "улица Ленина, 1"},
                "subtitle": {"text": "Витебск"},
            },
            {"title": None, "subtitle": None},
            "bad-item",
        ]
    }

    items = AddressSuggestService.normalize_results(payload)

    assert items == [
        {
            "title": "улица Ленина, 1",
            "subtitle": "Витебск",
            "value": "Витебск, улица Ленина, д. 1",
        }
    ]


def test_normalize_results_orders_city_street_house_from_yandex_title_subtitle():
    payload = {
        "results": [
            {
                "title": {"text": "6, 3-я Коллективная улица"},
                "subtitle": {"text": "Витебск"},
            }
        ]
    }

    items = AddressSuggestService.normalize_results(payload)

    assert items[0]["value"] == "Витебск, 3-я Коллективная улица, д. 6"


def test_normalize_results_keeps_object_name_before_address():
    payload = {
        "results": [
            {
                "title": {"text": "Банк, 6, 3-я Коллективная улица"},
                "subtitle": {"text": "Витебск"},
            }
        ]
    }

    items = AddressSuggestService.normalize_results(payload)

    assert items[0]["value"] == "Банк, Витебск, 3-я Коллективная улица, д. 6"


def test_normalize_results_uses_settlement_before_street_and_house():
    payload = {
        "results": [
            {
                "title": {"text": "Витебская улица, 14"},
                "subtitle": {"text": "агрогородок Новка, Новкинский сельсовет, Витебский район"},
            }
        ]
    }

    items = AddressSuggestService.normalize_results(payload)

    assert items[0]["value"] == "Витебский район, Новкинский сельсовет, агрогородок Новка, Витебская улица, д. 14"


def test_normalize_results_prefers_locality_over_region_for_objects():
    payload = {
        "results": [
            {
                "title": {"text": "Белагропромбанк"},
                "subtitle": {"text": "Витебская область, проспект Франциска Скорины, д. 8А"},
                "address": {
                    "components": [
                        {"name": "Беларусь", "kind": "country"},
                        {"name": "Витебская область", "kind": "province"},
                        {"name": "Полоцк", "kind": "locality"},
                        {"name": "проспект Франциска Скорины", "kind": "street"},
                        {"name": "8А", "kind": "house"},
                    ]
                },
            }
        ]
    }

    items = AddressSuggestService.normalize_results(payload)

    assert items[0]["value"] == "Белагропромбанк, Полоцк, проспект Франциска Скорины, д. 8А"


def test_normalize_results_keeps_locality_for_object_when_subtitle_starts_with_region():
    payload = {
        "results": [
            {
                "title": {"text": "Мясная Лавка"},
                "subtitle": {"text": "Витебская область, Борисовский тракт, д. 91"},
                "address": {
                    "components": [
                        {"name": "Витебская область", "kind": "province"},
                        {"name": "Лепель", "kind": "locality"},
                        {"name": "Борисовский тракт", "kind": "street"},
                        {"name": "91", "kind": "house"},
                    ]
                },
            }
        ]
    }

    items = AddressSuggestService.normalize_results(payload)

    assert items[0]["value"] == "Мясная Лавка, Лепель, Борисовский тракт, д. 91"
