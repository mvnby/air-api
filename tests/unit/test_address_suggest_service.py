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
        "улица Ленина, 1, Витебск",
        "улица Ленина, 1, Минск",
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
            "value": "улица Ленина, 1, Витебск",
        }
    ]
