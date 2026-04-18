from bs4 import BeautifulSoup
import pytest

from parsers.lg24 import Lg24Parser


def test_lg24_related_urls_use_item_tags_only():
    html = """
    <html>
      <body>
        <ul class="item-tags">
          <li><a href="/product/lg-eco-s07eqr/">LG ECO S07EQR</a></li>
          <li><a href="/product/lg-eco-s09eqr/">LG ECO S09EQR</a></li>
        </ul>
        <div class="related products">
          <a href="/product/noisy-extra-1/">Noisy 1</a>
          <a href="/product/noisy-extra-2/">Noisy 2</a>
        </div>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")

    related = Lg24Parser._collect_related_urls(soup, "https://lg24.by/product/current/")

    assert related == [
        "https://lg24.by/product/lg-eco-s07eqr/",
        "https://lg24.by/product/lg-eco-s09eqr/",
    ]


def test_lg24_extract_specs_skips_doc_download_rows():
    html = """
    <html>
      <body>
        <section id="tab1">
          <dl><dt>Руководство пользователя</dt><dd><a href="/file.pdf">Скачать</a></dd></dl>
          <dl><dt>Инструкция по монтажу</dt><dd>1 шт.</dd></dl>
          <dl><dt>Мощность охлаждения (Мин/Ном/Макс), кВт</dt><dd>0.89 / 2.5 / 3.7</dd></dl>
        </section>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")

    specs = Lg24Parser._extract_specs(soup)

    assert "Руководство пользователя" not in specs
    assert "Инструкция по монтажу" not in specs
    assert specs["Мощность охлаждения (Мин/Ном/Макс), кВт"] == "0.89 / 2.5 / 3.7"


def test_lg24_infers_type_and_indoor_type_from_breadcrumb():
    html = """
    <nav class="woocommerce-breadcrumb">
      <a href="/">Главная</a> /
      <a href="/catalog/dom">Кондиционеры для дома</a> /
      <a href="/catalog/dom/nastennye">Настенный блок</a> /
      Кондиционер LG ECO S07EQR
    </nav>
    """
    soup = BeautifulSoup(html, "html.parser")

    parts = Lg24Parser._extract_breadcrumb_parts(soup)
    inferred = Lg24Parser._infer_type_specs_from_breadcrumb(parts)

    assert inferred["Тип"] == "сплит-система"
    assert inferred["Тип внутреннего блока"] == "настенный"


def test_lg24_keeps_poluprom_type_when_present_in_breadcrumb():
    html = """
    <nav class="woocommerce-breadcrumb">
      <a href="/">Главная</a> /
      <a href="/catalog/poluprom">Полупром</a> /
      <a href="/catalog/poluprom/kanalnye">Канальный блок</a> /
      CL12R
    </nav>
    """
    soup = BeautifulSoup(html, "html.parser")

    parts = Lg24Parser._extract_breadcrumb_parts(soup)
    inferred = Lg24Parser._infer_type_specs_from_breadcrumb(parts)

    assert inferred["Тип"] == "полупромышленный кондиционер"
    assert inferred["Тип внутреннего блока"] == "канальный"


def test_lg24_defaults_non_wall_indoor_type_to_poluprom():
    html = """
    <nav class="woocommerce-breadcrumb">
      <a href="/">Главная</a> /
      <a href="/catalog/cassette">Кассетный блок</a> /
      UT48R
    </nav>
    """
    soup = BeautifulSoup(html, "html.parser")

    parts = Lg24Parser._extract_breadcrumb_parts(soup)
    inferred = Lg24Parser._infer_type_specs_from_breadcrumb(parts)

    assert inferred["Тип"] == "полупромышленный кондиционер"
    assert inferred["Тип внутреннего блока"] == "кассетный"


def test_lg24_title_brand_prefix_added_when_missing():
    normalized = Lg24Parser._normalize_model_title("Кондиционер Deluxe Pro H12S1D")
    assert normalized == "LG Deluxe Pro H12S1D"


def test_lg24_title_brand_prefix_not_duplicated_when_present():
    normalized = Lg24Parser._normalize_model_title("Кондиционер LG ECO Smart PC07SQR")
    assert normalized == "LG ECO Smart PC07SQR"


@pytest.mark.asyncio
async def test_lg24_parse_sets_fixed_lg_brand(monkeypatch):
    html = """
    <html>
      <body>
        <h1 class="product_title">4-поточный кассетный тип Ultra Inverter UT48R/UU48WR</h1>
        <meta itemprop="price" content="12345" />
        <section id="tab1">
          <dl><dt>Мощность охлаждения (Мин/Ном/Макс), кВт</dt><dd>5.0 / 13.4 / 14.0</dd></dl>
        </section>
      </body>
    </html>
    """

    class _Resp:
        status_code = 200
        text = html
        url = "https://lg24.by/product/ut48r-uu48wr/"

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            return _Resp()

    monkeypatch.setattr("parsers.lg24.httpx.AsyncClient", _FakeClient)

    parser = Lg24Parser()
    parsed = await parser.parse("https://lg24.by/product/ut48r-uu48wr/")

    assert parsed["specs"]["Бренд"] == "LG"
