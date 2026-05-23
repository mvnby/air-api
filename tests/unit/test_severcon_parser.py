import pytest

from parsers.severcon import SeverconEnergoluxParser
from services.importer_service import ImporterService


_XML = b"""<?xml version="1.0" encoding="windows-1251"?>
<yml_catalog>
  <shop>
    <categories>
      <category id="1">Energolux BADEN</category>
      <category id="2">\xdd\xeb\xe5\xea\xf2\xf0\xe8\xf7\xe5\xf1\xea\xe8\xe5 \xed\xe0\xe3\xf0\xe5\xe2\xe0\xf2\xe5\xeb\xe8 Energolux</category>
      <category id="3">\xca\xe0\xed\xe0\xeb\xfc\xed\xfb\xe5 \xe1\xeb\xee\xea\xe8</category>
    </categories>
    <offers>
      <offer id="101">
        <url>https://www.severcon.ru/catalog/energolux-test-sas09.html</url>
        <price>100000</price>
        <currencyId>RUB</currencyId>
        <categoryId>1</categoryId>
        <picture>https://cdn.example.com/main.png</picture>
        <vendor>Energolux</vendor>
        <name>\xc8\xed\xe2\xe5\xf0\xf2\xee\xf0\xed\xe0\xff \xf1\xe8\xf1\xf2\xe5\xec\xe0 \xea\xee\xed\xe4\xe8\xf6\xe8\xee\xed\xe8\xf0\xee\xe2\xe0\xed\xe8\xff Energolux TEST SAS09/SAU09</name>
        <description>\xd2\xe8\xf5\xe0\xff \xf0\xe0\xe1\xee\xf2\xe0&#10;\xcf\xf3\xeb\xfc\xf2 \xe2 \xea\xee\xec\xef\xeb\xe5\xea\xf2\xe5</description>
        <manufacturer_warranty>3 \xe3\xee\xe4\xe0</manufacturer_warranty>
        <param name="\xd5\xee\xeb\xee\xe4\xee\xef\xf0\xee\xe8\xe7\xe2\xee\xe4\xe8\xf2\xe5\xeb\xfc\xed\xee\xf1\xf2\xfc">2,64 (1,40~3,30)</param>
        <param name="\xd2\xe8\xef \xf3\xef\xf0\xe0\xe2\xeb\xe5\xed\xe8\xff \xea\xee\xec\xef\xf0\xe5\xf1\xf1\xee\xf0\xee\xec">On/Off</param>
        <param name="\xc2\xe0\xe9\xf4\xe0\xe9">\xce\xef\xf6\xe8\xee\xed\xe0\xeb\xfc\xed\xee</param>
        <param name="\xc1\xf0\xe5\xed\xe4">Energolux</param>
        <param name="\xc0\xf0\xf2\xe8\xea\xf3\xeb">SAS09/SAU09</param>
        <param name="\xc4\xee\xef. \xf4\xee\xf2\xee">https://cdn.example.com/extra-a.png, https://cdn.example.com/extra-b.png</param>
      </offer>
      <offer id="102">
        <price>5000</price>
        <currencyId>RUB</currencyId>
        <categoryId>2</categoryId>
        <vendor>Energolux</vendor>
        <name>\xdd\xeb\xe5\xea\xf2\xf0\xe8\xf7\xe5\xf1\xea\xe8\xe9 \xed\xe0\xe3\xf0\xe5\xe2\xe0\xf2\xe5\xeb\xfc Energolux SHRE</name>
      </offer>
      <offer id="103">
        <price>0.01</price>
        <currencyId>RUB</currencyId>
        <categoryId>3</categoryId>
        <vendor>Energolux</vendor>
        <name>\xca\xe0\xed\xe0\xeb\xfc\xed\xfb\xe9 \xe2\xed\xf3\xf2\xf0\xe5\xed\xed\xe8\xe9 \xe1\xeb\xee\xea Energolux SAD</name>
      </offer>
    </offers>
  </shop>
</yml_catalog>
"""


class _FakeResponse:
    status_code = 200
    content = _XML


class _FakeClient:
    def __init__(self, *args, **kwargs):  # noqa: ARG002
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url):  # noqa: ARG002
        return _FakeResponse()


@pytest.mark.asyncio
async def test_severcon_expands_feed_to_importable_energolux_offers(monkeypatch):
    monkeypatch.setattr("parsers.severcon.httpx.AsyncClient", _FakeClient)
    parser = SeverconEnergoluxParser()

    urls = await parser.get_import_urls(SeverconEnergoluxParser.FEED_URL)

    assert urls == [f"{SeverconEnergoluxParser.FEED_URL}#offer=101"]


@pytest.mark.asyncio
async def test_severcon_parses_offer_payload(monkeypatch):
    monkeypatch.setattr("parsers.severcon.httpx.AsyncClient", _FakeClient)
    parser = SeverconEnergoluxParser()

    data = await parser.parse(f"{SeverconEnergoluxParser.FEED_URL}#offer=101")

    assert data["title"] == "Energolux BADEN SAS09/SAU09"
    assert data["slug"] == "energolux-test-sas09"
    assert data["price"] == 100000
    assert data["price_currency"] == "RUB"
    assert data["main_image"] == "https://cdn.example.com/main.png"
    assert data["images"] == [
        "https://cdn.example.com/extra-a.png",
        "https://cdn.example.com/extra-b.png",
    ]
    assert data["save_gallery"] is True
    assert data["specs"]["Бренд"] == "Energolux"
    assert data["specs"]["Серия"] == "BADEN"
    assert data["specs"]["Тип"] == "сплит-система"
    assert data["metrics"]["area"] == 26
    assert data["metrics"]["is_inverter"] is False
    assert data["metrics"]["power_cooling"] == 2.64


def test_severcon_extracts_series_from_supplier_categories():
    assert SeverconEnergoluxParser._series_from_category("Energolux BADEN") == "BADEN"
    assert (
        SeverconEnergoluxParser._series_from_category(
            "Настенный блок Energolux Smart Multi серия GENEVA"
        )
        == "GENEVA"
    )
    assert (
        SeverconEnergoluxParser._series_from_category("ENERGOLUX FLOOR-CEILING-WS30 6 серия")
        == "FLOOR-CEILING-WS30 6"
    )
    assert SeverconEnergoluxParser._series_from_category("Кассетные блоки") == ""


def test_severcon_formats_catalog_titles_by_product_kind():
    split_title = SeverconEnergoluxParser._display_title(
        raw_title="Классическая система кондиционирования Energolux BADEN SAS07BD1-A/SAU07BD1-A",
        category="Energolux BADEN",
        specs={
            "Бренд": "Energolux",
            "Серия": "BADEN",
            "Тип": "сплит-система",
            "Артикул": "SAS07BD1-A/SAU07BD1-A",
        },
    )
    assert split_title == "Energolux BADEN SAS07BD1-A/SAU07BD1-A"

    multi_title = SeverconEnergoluxParser._display_title(
        raw_title="Настенные блоки Smart Multi Energolux SAS09M3-AI",
        category="Настенный блок Energolux Smart Multi серия GENEVA",
        specs={
            "Бренд": "Energolux",
            "Серия": "GENEVA",
            "Тип": "внутренний блок",
            "Тип внутреннего блока": "настенный",
            "Артикул": "SAS09M3-AI",
        },
    )
    assert multi_title == "Внутренний блок Energolux GENEVA SAS09M3-AI"

    semi_title = SeverconEnergoluxParser._display_title(
        raw_title="Напольно-потолочная сплит-система Energolux SAСF18D6-A / SAU18U6-A",
        category="ENERGOLUX FLOOR-CEILING 6 серия",
        specs={
            "Бренд": "Energolux",
            "Серия": "FLOOR-CEILING 6",
            "Тип": "сплит-система",
            "Тип внутреннего блока": "напольно-потолочный",
            "Модель внутреннего блока": "SAСF18D6-A",
            "Модель наружного блока": "SAU18U6-A",
        },
    )
    assert semi_title == "Напольно-потолочный кондиционер Energolux FLOOR-CEILING 6 SAСF18D6-A/SAU18U6-A"

    article_title = SeverconEnergoluxParser._display_title(
        raw_title="Кассетная сплит-система Energolux Cassete 6 SAС12С6-A / SAU12U6-A",
        category="ENERGOLUX CASSETE 6 серия",
        specs={
            "Бренд": "Energolux",
            "Серия": "CASSETE 6",
            "Тип": "сплит-система",
            "Тип внутреннего блока": "кассетный",
            "Модель внутреннего блока": "SAС12С6-A",
            "Модель наружного блока": "SAU12U5-A",
            "Артикул": "SAС12С6-A/SAU12U6-A",
        },
    )
    assert article_title == "Кассетный кондиционер Energolux CASSETE 6 SAС12С6-A/SAU12U6-A"


def test_severcon_reconciles_model_pair_from_article_when_source_params_disagree():
    specs = {
        "Артикул": "SAС12С6-A/SAU12U6-A",
        "Модель внутреннего блока": "SAС12С6-A",
        "Модель наружного блока": "SAU12U5-A",
    }

    SeverconEnergoluxParser._reconcile_models_from_article(specs)

    assert specs["Модель внутреннего блока"] == "SAС12С6-A"
    assert specs["Модель наружного блока"] == "SAU12U6-A"


@pytest.mark.asyncio
async def test_importer_bulk_expands_supported_feed_urls(monkeypatch):
    class _ExpandingParser:
        def supports(self, url):
            return url == "https://example.com/feed.xml"

        async def get_import_urls(self, url):  # noqa: ARG002
            return ["https://example.com/feed.xml#offer=1", "https://example.com/feed.xml#offer=2"]

    service = ImporterService()
    service.parsers = [_ExpandingParser()]
    imported = []
    progress_events = []

    async def _fake_import_product(url, update_existing=False, collect_related=False):  # noqa: ARG001
        imported.append(url)
        return {"product": type("ProductStub", (), {"title": url, "id": len(imported)})(), "related_urls": []}

    async def _capture_progress(payload):
        progress_events.append(payload)

    monkeypatch.setattr(service, "import_product", _fake_import_product)

    result = await service.import_products_bulk(
        ["https://example.com/feed.xml"],
        progress_callback=_capture_progress,
    )

    assert imported == ["https://example.com/feed.xml#offer=1", "https://example.com/feed.xml#offer=2"]
    assert result["errors"] == []
    assert len(result["success"]) == 2
    assert progress_events[0]["stage"] == "expanding"
    assert any(event["stage"] == "expanded" and event["total"] == 2 for event in progress_events)
    assert progress_events[-1]["stage"] == "completed"
    assert progress_events[-1]["processed"] == 2
