import pytest

from parsers.mdv_catalog import MDV_EXPORT_URLS, MDV_PROMOTED_PROP_KEYS, MdvCatalogParser, MdvCatalogRecord
from services.supplier_match_service import build_product_match_profile


HOUSEHOLD_ITEM = {
    "ID": "1",
    "NAME": "MDSAJ-07HRFN8/MDOAJ-07HFN8",
    "CODE": "mdsaj-07hrfn8-mdoaj-07hfn8",
    "PREVIEW_PICTURE": "/upload/main-household.png",
    "DETAIL_PICTURE": "",
    "SECTIONS": {
        "SECTION_1": "Бытовые сплит-системы MDV для дома и офиса",
        "SECTION_2": "Инверторные сплит-системы MDV",
        "SECTION_3": "iERA inverter",
    },
    "BASE_PRICE": "46300.00000000",
    "PROPERTIES": {
        "UNIT_INDOOR": "MDSAJ-07HRFN8",
        "UNIT_OUTDOOR": "MDOAJ-07HFN8",
        "COMPRESSOR_OPER_TYPE": "3D DC-Inverter",
        "COOLING_NOM": "2,05",
        "HEATING_NOM": "2,34",
        "DRAIN_PIPE_OUT_DIAMETER": "16",
        "NOMINAL_CURRENT_COOLING": "3,2",
        "NOMINAL_CURRENT_HEATING": "2,9",
        "CLASS_EE_COOLING": "A++",
        "PIPE_LIQUID_SIZE_INCH": "1/4",
        "PIPE_GAZ_SIZE_INCH": "3/8",
        "MORE_PHOTO": "/upload/gallery-a.png,/upload/gallery-b.png",
    },
}


MULTI_INDOOR_ITEM = {
    "ID": "2",
    "NAME": "MDSAI2-09HRFN8",
    "CODE": "mdsai2-09hrfn8-",
    "PREVIEW_PICTURE": "/upload/main-indoor.png",
    "DETAIL_PICTURE": "",
    "SECTIONS": {
        "SECTION_1": "Мультисплит-системы MDV",
        "SECTION_2": "Настенные внутренние блоки",
        "SECTION_3": "INTEGRA Pro",
    },
    "BASE_PRICE": "18600.00000000",
    "PROPERTIES": {
        "UNIT_INDOOR": "MDSAI2-09HRFN8",
        "COOLING_NOM": "2,64",
        "HEATING_NOM": "2,93",
        "MORE_PHOTO": "/upload/indoor-gallery.png",
    },
}


MULTI_OUTDOOR_ITEM = {
    "ID": "3",
    "NAME": "MD2O-18HFN8",
    "CODE": "md2o-18hfn8",
    "PREVIEW_PICTURE": "/upload/main-outdoor.png",
    "DETAIL_PICTURE": "",
    "SECTIONS": {
        "SECTION_2": "Мультисплит-системы MDV",
        "SECTION_3": "Наружные блоки",
    },
    "BASE_PRICE": "128200.00000000",
    "PROPERTIES": {
        "UNIT_OUTDOOR": "MD2O-18HFN8",
        "COOLING_NOM": "5,28",
        "HEATING_NOM": "5,57",
        "CLASS_EE_COOLING": "A++",
    },
}


SITEMAP_XML = """
<urlset>
  <url><loc>https://mdv-aircond.ru/catalog/bytovye-split-sistemy/invertornye-split-sistemy/iera/mdsaj-07hrfn8-mdoaj-07hfn8/</loc></url>
  <url><loc>https://mdv-aircond.ru/catalog/multisplit-sistemy/nastennye-vnutrennie-bloki/integra-pro2820/mdsai2-09hrfn8-/</loc></url>
  <url><loc>https://mdv-aircond.ru/catalog/multisplit-sistemy/naruzhnye-bloki/md2o-18hfn8/</loc></url>
</urlset>
"""


class _FakeResponse:
    def __init__(self, *, json_data=None, text="", status_code=200):
        self._json_data = json_data
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._json_data


class _FakeClient:
    def __init__(self, *args, **kwargs):  # noqa: ARG002
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):  # noqa: ARG002
        if url == MDV_EXPORT_URLS["household"]:
            return _FakeResponse(json_data=[HOUSEHOLD_ITEM])
        if url == MDV_EXPORT_URLS["multi"]:
            return _FakeResponse(json_data=[MULTI_INDOOR_ITEM, MULTI_OUTDOOR_ITEM])
        if url == MDV_EXPORT_URLS["semi"]:
            return _FakeResponse(json_data=[])
        if url.endswith("sitemap-iblock-11.xml"):
            return _FakeResponse(text=SITEMAP_XML)
        if url.endswith("mdsaj-07hrfn8-mdoaj-07hfn8/"):
            return _FakeResponse(
                text='<a href="/upload/manual-a.pdf"></a><a href="/upload/manual-b.pdf"></a>'
            )
        return _FakeResponse(text="")


@pytest.mark.asyncio
async def test_mdv_catalog_expands_export_to_sitemap_product_urls(monkeypatch):
    monkeypatch.setattr("parsers.mdv_catalog.httpx.AsyncClient", _FakeClient)
    parser = MdvCatalogParser()

    urls = await parser.get_import_urls(MDV_EXPORT_URLS["household"])

    assert urls == [
        "https://mdv-aircond.ru/catalog/bytovye-split-sistemy/invertornye-split-sistemy/iera/mdsaj-07hrfn8-mdoaj-07hfn8/"
    ]


@pytest.mark.asyncio
async def test_mdv_catalog_parses_household_product_with_gallery_and_manuals(monkeypatch):
    monkeypatch.setattr("parsers.mdv_catalog.httpx.AsyncClient", _FakeClient)
    parser = MdvCatalogParser()

    data = await parser.parse(
        "https://mdv-aircond.ru/catalog/bytovye-split-sistemy/invertornye-split-sistemy/iera/mdsaj-07hrfn8-mdoaj-07hfn8/"
    )

    assert data["title"] == "MDV iERA inverter MDSAJ-07HRFN8/MDOAJ-07HFN8"
    assert data["price"] == 46300
    assert data["price_currency"] == "RUB"
    assert data["main_image"] == "https://mdv-aircond.ru/upload/main-household.png"
    assert data["require_media_download"] is True
    assert data["images"] == [
        "https://mdv-aircond.ru/upload/gallery-a.png",
        "https://mdv-aircond.ru/upload/gallery-b.png",
    ]
    assert data["manuals"] == [
        {
            "kind": "manual",
            "title": "Инструкция MDV",
            "url": "https://mdv-aircond.ru/upload/manual-a.pdf",
            "source": "mdv",
        },
        {
            "kind": "manual",
            "title": "Инструкция MDV 2",
            "url": "https://mdv-aircond.ru/upload/manual-b.pdf",
            "source": "mdv",
        },
    ]
    assert data["specs"]["type"] == "сплит-система"
    assert data["specs"]["model_indoor"] == "MDSAJ-07HRFN8"
    assert data["specs"]["model_outdoor"] == "MDOAJ-07HFN8"
    assert data["specs"]["current_cooling_nominal_a"] == "3,2"
    assert data["specs"]["current_heating_nominal_a"] == "2,9"
    assert data["specs"]["pipe_liquid"] == "1/4"
    assert data["specs"]["pipe_gas"] == "3/8"
    assert data["specs"]["drain_pipe_diameter"] == "16"
    assert data["specs"]["mdv_rrc_rub"] == 46300
    assert data["specs"]["__mdv_catalog"] == "household"
    assert "COOLING_NOM" in data["specs"]["__mdv_raw_specs"]


@pytest.mark.asyncio
async def test_mdv_catalog_parses_multi_indoor_and_outdoor_types(monkeypatch):
    monkeypatch.setattr("parsers.mdv_catalog.httpx.AsyncClient", _FakeClient)
    parser = MdvCatalogParser()

    indoor = await parser.parse(
        "https://mdv-aircond.ru/catalog/multisplit-sistemy/nastennye-vnutrennie-bloki/integra-pro2820/mdsai2-09hrfn8-/"
    )
    outdoor = await parser.parse(
        "https://mdv-aircond.ru/catalog/multisplit-sistemy/naruzhnye-bloki/md2o-18hfn8/"
    )

    assert indoor["title"] == "Внутренний блок MDV INTEGRA Pro MDSAI2-09HRFN8"
    assert indoor["specs"]["type"] == "внутренний блок"
    assert indoor["specs"]["indoor_type"] == "настенный"
    assert outdoor["title"] == "Наружный блок MDV MD2O-18HFN8"
    assert outdoor["specs"]["type"] == "наружный блок"


def test_mdv_catalog_preserves_console_indoor_form_factor():
    assert MdvCatalogParser._infer_indoor_type("Полупромышленные консольные блоки") == "консольный"
    assert MdvCatalogParser._inner_block_label("консольный") == "Внутренний консольный блок"
    assert MdvCatalogParser._semi_descriptor("консольный") == "Консольный"


@pytest.mark.parametrize(
    ("section_3", "expected"),
    [
        ("Инверторные канальные сплит-системы MDT2II", "канальный"),
        ("Кассетные однопоточные сплит-системы MDCA1I", "кассетный"),
        ("Консольные сплит-системы MDFFI", "консольный"),
    ],
)
def test_mdv_household_uses_specific_indoor_section(section_3, expected):
    item = {
        "SECTIONS": {
            "SECTION_1": "Бытовые сплит-системы MDV",
            "SECTION_2": "Кассетные, канальные, консольные сплит-системы",
            "SECTION_3": section_3,
        },
        "PROPERTIES": {"UNIT_INDOOR": "MDCA1I-12HRFN8", "UNIT_OUTDOOR": "MDOAG-12HFN8"},
    }
    record = MdvCatalogRecord(catalog="household", item=item, source_url="")

    assert MdvCatalogParser()._system_type_specs(record)["indoor_type"] == expected


def test_mdv_household_does_not_guess_from_mixed_section():
    item = {"SECTIONS": {"SECTION_2": "Кассетные, канальные, консольные сплит-системы"}}
    record = MdvCatalogRecord(catalog="household", item=item, source_url="")

    assert "indoor_type" not in MdvCatalogParser()._system_type_specs(record)


def test_mdv_multi_console_uses_console_section():
    item = {
        "SECTIONS": {
            "SECTION_1": "Мультисплит-системы MDV",
            "SECTION_2": "Консольные блоки",
            "SECTION_3": "Консольные внутренние блоки",
        },
        "PROPERTIES": {"UNIT_INDOOR": "MDFFI-12HRFN8"},
    }
    record = MdvCatalogRecord(catalog="multi", item=item, source_url="")

    assert MdvCatalogParser()._system_type_specs(record) == {
        "type": "внутренний блок",
        "indoor_type": "консольный",
    }


def test_mdv_price_wifi_override_requires_exact_model_pair():
    item = {
        "SECTIONS": {"SECTION_3": "INFINI Loft ERP Inverter"},
        "PROPERTIES": {"UNIT_INDOOR": "MDSALF-09HRFN8", "UNIT_OUTDOOR": "MDOALF-09HFN8"},
    }
    record = MdvCatalogRecord(catalog="household", item=item, source_url="")
    parser = MdvCatalogParser()

    assert parser._build_specs(record)["wifi_ready"] == "ready"
    item["PROPERTIES"]["UNIT_OUTDOOR"] = "OTHER-09HFN8"
    assert "wifi_ready" not in parser._build_specs(record)


@pytest.mark.parametrize(
    ("indoor", "outdoor", "catalog", "expected"),
    [
        ("MDSC-09HRDN8", "MDOC-09HDN8", "household", "builtin"),
        ("MDSC-12HRDN8", "MDOC-12HDN8", "household", "ready"),
        ("MDSAN-18HRFN8", "MDOAN-18HFN8", "household", "ready"),
        ("MDSAJ-07HRFN8", "MDOAJ-07HFN8", "household", "builtin"),
        ("MDSAJ-07HRFN8", None, "multi", "builtin"),
    ],
)
def test_user_confirmed_mdv_wifi_survives_reimport(indoor, outdoor, catalog, expected):
    properties = {"UNIT_INDOOR": indoor}
    if outdoor:
        properties["UNIT_OUTDOOR"] = outdoor
    record = MdvCatalogRecord(
        catalog=catalog,
        item={"SECTIONS": {"SECTION_3": "iERA inverter"}, "PROPERTIES": properties},
        source_url="",
    )

    assert MdvCatalogParser()._build_specs(record)["wifi_ready"] == expected


def test_mdv_promoted_keys_cover_supplier_mapping_fields():
    for key in (
        "UNIT_INDOOR",
        "UNIT_OUTDOOR",
        "SIZE_INDOOR_WIDTH",
        "SIZE_OUTDOOR_WIDTH",
        "COOLING_NOM",
        "NOMINAL_CURRENT_COOLING",
        "PIPE_LIQUID_SIZE_INCH",
        "PIPE_GAZ_SIZE_INCH",
        "DRAIN_PIPE_OUT_DIAMETER",
        "MORE_PHOTO",
    ):
        assert key in MDV_PROMOTED_PROP_KEYS


def test_mdv_product_specs_feed_supplier_match_profile():
    product = {
        "title": "MDV iERA inverter MDSAJ-07HRFN8/MDOAJ-07HFN8",
        "specs": {
            "model_indoor": "MDSAJ-07HRFN8",
            "model_outdoor": "MDOAJ-07HFN8",
        },
    }

    profile = build_product_match_profile(product)

    assert "MDSAJ-07HRFN8" in profile.model_tokens
    assert "MDOAJ-07HFN8" in profile.model_tokens
    assert "MDSAJ-07HRFN8" in profile.indoor_model_tokens
    assert "MDOAJ-07HFN8" in profile.outdoor_model_tokens
