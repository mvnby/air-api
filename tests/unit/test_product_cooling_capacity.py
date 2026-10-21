import pytest

from parsers.aircond import AircondParser
from parsers.haierproff import HaierProffParser
from parsers.hobot import HobotParser
from parsers.lg24 import Lg24Parser
from parsers.onliner import OnlinerParser
from parsers.tvoy_klimat import TvoyKlimatParser
from services.product_cooling_capacity import nominal_cooling_capacity


@pytest.mark.parametrize("raw,expected", [
    ("16.12", 16.12), ("16,12 кВт", 16.12),
    ("16120 Вт", 16.12), ("3.68 / 10.50 / 11.03", 10.5),
])
def test_canonical_nominal_capacity_wins_over_consumption_and_modulation(raw, expected):
    assert nominal_cooling_capacity({
        "capacity_cooling_kw": raw,
        "power_cons_cooling_kw": "5.69",
        "capacity_cooling_max_kw": "18",
    }, fallback=5.69) == expected


@pytest.mark.parametrize("invalid", [None, "неизвестно", True, float("nan"), -1, 0])
def test_invalid_capacity_does_not_become_zero_or_electrical_consumption(invalid):
    assert nominal_cooling_capacity({"capacity_cooling_kw": invalid, "power_cons_cooling_kw": "5.69"}) is None


@pytest.mark.parametrize("extract", [
    lambda specs: AircondParser._build_metrics(specs),
    lambda specs: HaierProffParser._extract_metrics(specs, "TCL 60"),
    lambda specs: HobotParser._extract_metrics(specs, "TCL 60"),
    lambda specs: Lg24Parser._extract_metrics(specs, "TCL 60"),
])
def test_parser_metrics_do_not_overwrite_capacity_with_later_consumption(extract):
    metrics = extract({
        "Мощность охлаждения, кВт": "16.12",
        "Потребляемая мощность охлаждения, кВт": "5.69",
        "Мощность обогрева, кВт": "17.00",
        "Потребляемая мощность обогрева, кВт": "5.80",
    })
    assert metrics["power_cooling"] == 16.12
    assert metrics["power_heating"] == 17.0
    assert extract({"Потребляемая мощность охлаждения, кВт": "5.69"})["power_cooling"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("parser,url", [
    (OnlinerParser(), "https://catalog.onliner.by/conditioners/tcl/test60"),
    (TvoyKlimatParser(), "https://tvoy-klimat.by/catalog/test60/"),
])
async def test_html_parsers_keep_nominal_when_consumption_row_follows(monkeypatch, parser, url):
    html = '''<html><h1>TCL 60</h1>
    <table class="product-specs__table">
      <tr><td>Мощность охлаждения</td><td>16.12 кВт</td></tr>
      <tr><td>Потребляемая мощность охлаждения</td><td>5.69 кВт</td></tr>
    </table>
    <div class="properties-group__item"><div class="properties-group__name">Мощность охлаждения</div><div class="properties-group__value">16.12</div></div>
    <div class="properties-group__item"><div class="properties-group__name">Потребляемая мощность охлаждения</div><div class="properties-group__value">5.69</div></div>
    </html>'''

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            import httpx
            return httpx.Response(200, text=html if "api" not in url else '{}', request=httpx.Request("GET", url))

    monkeypatch.setattr("httpx.AsyncClient", Client)
    data = await parser.parse(url)
    assert data["metrics"]["power_cooling"] == 16.12
