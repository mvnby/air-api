from bs4 import BeautifulSoup

from parsers.hisense_catalog import HisenseCatalogParser
from services.hisense_price_service import append_model_fragment, parse_hisense_price_sheet
from services.spec_normalizer import normalize_specs
from services.supplier_match_service import (
    _infer_offer_catalog_categories,
    _product_catalog_category,
    build_offer_match_profile,
)
from services.xlsx_reader import XlsxCell, XlsxSheet


def _row(values, *, link_idx: int | None = None, link: str | None = None):
    cells = []
    for idx, value in enumerate(values):
        cells.append(XlsxCell(str(value), hyperlink=link if idx == link_idx else None))
    return cells


def test_hisense_price_sheet_inherits_series_hyperlink_to_model_rows():
    sheet = XlsxSheet(
        name="КРАТКИЙ ПРАЙС СПЛИТЫ",
        rows=[
            _row(["Серия", "", "", "", "", "", "", "", "", "Узнать больше"], link_idx=9, link="https://hisense-air.ru/product/vision/"),
            _row(["AS-10UW4RXVQH01A", "", "", "", "", "", "", "", "4400", "3243", "", "12"]),
        ],
    )

    offers = parse_hisense_price_sheet(sheet)

    assert len(offers) == 1
    assert offers[0].external_id == "AS-10UW4RXVQH01A"
    assert offers[0].series_title == "Серия"
    assert offers[0].source_url == "https://hisense-air.ru/product/vision#model=AS-10UW4RXVQH01A"
    assert offers[0].rrc_byn == 4400
    assert offers[0].wholesale_value == 3243
    assert offers[0].qty == 12


def test_append_model_fragment_escapes_parentheses():
    assert (
        append_model_fragment("https://hisense-air.ru/product/carbon/", "AS-10UW4RXVQH01A(B)")
        == "https://hisense-air.ru/product/carbon#model=AS-10UW4RXVQH01A%28B%29"
    )


def test_hisense_catalog_extracts_model_specs_media_and_normalized_aliases():
    html = """
    <html>
      <body>
        <h1 class="product-full-title">VISION PRO</h1>
        <div class="small-desc">Краткое описание серии.</div>
        <ul class="article-list"><li>Управление Wi-Fi.</li><li>Тихий режим.</li></ul>
        <img src="https://images.breez.ru/catalog/hisense/vision/vision-01.png" />
        <a href="/manual.pdf">Скачать инструкцию</a>
        <table class="techtable">
          <tr><td>Выбрать модель AS-10UW4RXVQH01A AS-13UW4RXVQH02</td><td>AS-10UW4RXVQH01A</td><td>AS-13UW4RXVQH02</td></tr>
          <tr><td>Бренд</td><td>Hisense</td><td>Hisense</td></tr>
          <tr><td>Модель внутреннего блока</td><td>AS-10G</td><td>AS-13G</td></tr>
          <tr><td>Модель наружного блока</td><td>AS-10W</td><td>AS-13W</td></tr>
          <tr><td>Серия</td><td>VISION PRO</td><td>VISION PRO</td></tr>
          <tr><td>Тип внутреннего блока</td><td>Настенный</td><td>Настенный</td></tr>
          <tr><td>Холодопроизводительность (кВт) кВт</td><td>2.80</td><td>3.70</td></tr>
          <tr><td>Теплопроизводительность (кВт) кВт</td><td>3.50</td><td>4.20</td></tr>
          <tr><td>Расход воздуха внутреннего блока м 3 /ч</td><td>580</td><td>620</td></tr>
          <tr><td>Уровень шума внутреннего блока дБ(А)</td><td>18</td><td>20</td></tr>
          <tr><td>Габаритные размеры внутреннего блока (ШxВxГ) мм</td><td>877x301x194</td><td>900x310x200</td></tr>
          <tr><td>Срок гарантии мес.</td><td>36</td><td>36</td></tr>
        </table>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")

    models = HisenseCatalogParser._extract_models(soup)
    raw_specs = HisenseCatalogParser._extract_model_specs(soup, "AS-13UW4RXVQH02")
    specs = normalize_specs(
        HisenseCatalogParser._augment_specs(
            raw_specs,
            model="AS-13UW4RXVQH02",
            series_title="VISION PRO",
            source_url="https://hisense-air.ru/product/vision",
        ),
        title="Hisense AS-13UW4RXVQH02",
    )

    assert models == ["AS-10UW4RXVQH01A", "AS-13UW4RXVQH02"]
    assert specs["model_indoor"] == "AS-13G"
    assert specs["model_outdoor"] == "AS-13W"
    assert specs["capacity_cooling_kw"] == "3.70"
    assert specs["capacity_heating_kw"] == "4.20"
    assert specs["airflow_max"] == "620"
    assert specs["noise_indoor"] == "20"
    assert specs["warranty_months"] == "36"
    assert specs["width_indoor"] == "900"
    assert specs["height_indoor"] == "310"
    assert specs["depth_indoor"] == "200"
    assert HisenseCatalogParser._extract_images(soup, "https://hisense-air.ru/product/vision") == [
        "https://images.breez.ru/catalog/hisense/vision/vision-01.png"
    ]
    assert HisenseCatalogParser._extract_manuals(soup, "https://hisense-air.ru/product/vision")[0]["url"] == (
        "https://hisense-air.ru/manual.pdf"
    )


def test_hisense_supplier_matching_understands_multi_and_semi_context():
    profile = build_offer_match_profile("Hisense AMW2-14U4RGC · НАРУЖНЫЕ БЛОКИ MULTI EU DC Inverter")
    assert "AMW2-14U4RGC" in profile.outdoor_model_tokens

    assert (
        _infer_offer_catalog_categories(
            source_name="КРАТКИЙ ПРАЙС СПЛИТЫ",
            title_raw="Hisense AUW-36U4R · СПЛИТ-СИСТЕМЫ КАССЕТНОГО ТИПА A++",
        )
        == {"semi"}
    )
    assert (
        _product_catalog_category(
            {
                "title": "Hisense AMW2-14U4RGC",
                "specs": {"__hisense_catalog": "multi", "type": "наружный блок"},
            }
        )
        == "multi"
    )
