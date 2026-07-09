import pytest

from parsers.aircond import AircondParser
from services.spec_normalizer import normalize_specs
from services.spec_registry import REGISTRY_DIMENSIONS_MAP, REGISTRY_KEY_MAP


AIRCOND_MODERN_PRODUCT_HTML = """
<html>
  <head>
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Сплит-система TCL SaveIN AI Inverter Wi-Fi TAC-09CHSD/ZG11IHB",
        "offers": {"@type": "Offer", "priceCurrency": "BYN", "price": 1850},
        "image": [
          "https://cdn.aircond.by/series/129/main.webp",
          "https://cdn.aircond.by/series/129/side.webp"
        ],
        "description": "TCL SaveIN AI Inverter создает микроклимат в помещениях до 25 м²."
      }
    </script>
  </head>
  <body>
    <h1 class="page-title lg:row-span-2">Сплит-система TCL SaveIN AI Inverter Wi-Fi TAC-09CHSD/ZG11IHB</h1>
    <img src="https://cdn.aircond.by/series/129/thumb-main.webp" alt="thumb" />
    <img src="https://cdn.aircond.by/series/129/main.webp" alt="main" />
    <img src="/images/payment-methods.png" alt="payment" />
    <a class="border-border rounded-md border px-3 py-1" href="/split-sistemy/tcl-savein-ai-inverter-tac-12chsdzg11ihb/">35 м²</a>
    <a class="border-border rounded-md border px-3 py-1" href="/split-sistemy/tcl-savein-ai-inverter-wi-fi-tac-09chsdzg41ihb/">черный</a>

    <section class="space-y-6 mb-6">
      <h2 class="text-xl font-semibold md:text-2xl">Характеристики</h2>
      <div>
        <h3 class="mb-2 text-lg font-medium">Основные</h3>
        <div class="space-y-0">
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Тип</span><span class="max-w-lg text-right font-medium"><span>сплит-система</span></span>
          </div>
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Бренд</span><span class="max-w-lg text-right font-medium"><span>TCL</span></span>
          </div>
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Год модели</span><span class="max-w-lg text-right font-medium"><span>2026</span></span>
          </div>
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Инвертор</span>
            <span class="max-w-lg text-right font-medium"><svg class="lucide lucide-check size-4.5 text-emerald-500"></svg></span>
          </div>
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Wi-Fi</span>
            <span class="max-w-lg text-right font-medium"><svg class="lucide lucide-check size-4.5 text-emerald-500"></svg></span>
          </div>
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Функции</span>
            <span class="max-w-lg text-right font-medium"><span>T-AI Energy Saving, Coanda Airflow, самоочистка</span></span>
          </div>
        </div>
      </div>
      <div>
        <h3 class="mb-2 text-lg font-medium">Производительность</h3>
        <div class="space-y-0">
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Обслуживаемая площадь</span><span class="max-w-lg text-right font-medium"><span>25 м²</span></span>
          </div>
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Мощность охлаждения</span><span class="max-w-lg text-right font-medium"><span>2.62 кВт</span></span>
          </div>
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Рабочая температура при обогреве</span><span class="max-w-lg text-right font-medium"><span>-20...+30 °C</span></span>
          </div>
        </div>
      </div>
      <div>
        <h3 class="mb-2 text-lg font-medium">Габариты</h3>
        <div class="space-y-0">
          <div class="-mx-3 grid grid-cols-[1fr_auto] gap-3 border-b px-3 py-2.5 text-sm">
            <span class="text-neutral-600">Габариты внутреннего блока (Ш×В×Г)</span><span class="max-w-lg text-right font-medium"><span>778 × 272 × 192 мм</span></span>
          </div>
        </div>
      </div>
    </section>
  </body>
</html>
"""


class _FakeResponse:
    status_code = 200
    text = AIRCOND_MODERN_PRODUCT_HTML


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
async def test_aircond_parser_handles_current_product_markup(monkeypatch):
    monkeypatch.setattr("parsers.aircond.httpx.AsyncClient", _FakeClient)

    data = await AircondParser().parse(
        "https://aircond.by/split-sistemy/tcl-savein-ai-inverter-tac-09chsdzg11ihb/"
    )

    assert data["title"] == "Сплит-система TCL SaveIN AI Inverter Wi-Fi TAC-09CHSD/ZG11IHB"
    assert data["price"] == 1850
    assert data["main_image"] == "https://cdn.aircond.by/series/129/main.webp"
    assert data["images"] == ["https://cdn.aircond.by/series/129/side.webp"]
    assert data["related_urls"] == [
        "https://aircond.by/split-sistemy/tcl-savein-ai-inverter-tac-12chsdzg11ihb/",
        "https://aircond.by/split-sistemy/tcl-savein-ai-inverter-wi-fi-tac-09chsdzg41ihb/",
    ]
    assert data["specs"]["Инвертор"] == "да"
    assert data["specs"]["Wi-Fi"] == "да"
    assert data["metrics"]["power_cooling"] == 2.62
    assert data["metrics"]["area"] == 25
    assert data["metrics"]["min_temp_heating"] == -20

    normalized = normalize_specs(data["specs"], title=data["title"], auto_tag_slugs=[])
    unmapped = {
        key: value
        for key, value in data["specs"].items()
        if key not in REGISTRY_KEY_MAP and key not in REGISTRY_DIMENSIONS_MAP and key not in normalized
    }

    assert unmapped == {}
    assert normalized["release_year"] == "2026"
    assert normalized["inverter"] is True
    assert normalized["wifi_state"] == "builtin"
    assert normalized["features"] == "T-AI Energy Saving, Coanda Airflow, самоочистка"
    assert normalized["capacity_cooling_kw"] == "2.62"
    assert normalized["temp_range_heat"] == "-20...+30 °C"
    assert normalized["width_indoor"] == "778"
    assert normalized["height_indoor"] == "272"
    assert normalized["depth_indoor"] == "192"
