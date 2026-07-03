import pytest

from parsers.mdv_catalog import MDV_EXPORT_URLS, MDV_PROMOTED_PROP_KEYS, MdvCatalogParser
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
