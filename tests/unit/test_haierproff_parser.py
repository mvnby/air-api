from bs4 import BeautifulSoup

from parsers.haierproff import HaierProffParser


def test_haierproff_infers_poluprom_and_universal_indoor_from_breadcrumbs():
    parts = [
        "Каталог",
        "Полупромышленные сплит-системы",
        "Super Match Plus",
        "AC105S2SH2FA / 1U105S2SS1FB",
    ]
    title = "Haier AC105S2SH2FA / 1U105S2SS1FB AC (Универсальные блоки) Super Match Plus"

    inferred = HaierProffParser._infer_type_specs_from_breadcrumb_and_title(
        title=title,
        breadcrumb_parts=parts,
    )

    assert inferred["Тип"] == "Полупромышленный кондиционер"
    assert inferred["Тип внутреннего блока"] == "Напольно-потолочный"


def test_haierproff_infers_household_for_wall_from_title_only():
    inferred = HaierProffParser._infer_type_specs_from_breadcrumb_and_title(
        title="Haier AS35S2SJ2FA Jade настенный блок",
        breadcrumb_parts=[],
    )

    assert inferred["Тип"] == "Сплит-система"
    assert inferred["Тип внутреннего блока"] == "Настенный"


def test_haierproff_defaults_split_system_to_wall_indoor_type():
    inferred = HaierProffParser._infer_type_specs_from_breadcrumb_and_title(
        title="Haier HSU-24HQJ103/R3 Quantum On-Off",
        breadcrumb_parts=["Каталог", "Бытовые сплит-системы"],
    )

    assert inferred["Тип"] == "Сплит-система"
    assert inferred["Тип внутреннего блока"] == "Настенный"


def test_haierproff_detects_wifi_by_feature_title_and_icon():
    entries = [
        {"img": "/images/uploads/2023/04/12/resize_cache/46_1/44cdb19d3e20378d090e233fdcc44d44.png", "title": "", "desc": "", "text": ""},
        {"img": "", "title": "Управление Wi-Fi (Стандартно)", "desc": "", "text": "Управление Wi-Fi (Стандартно)"},
    ]

    assert HaierProffParser._feature_entries_indicate_wifi(entries) is True


def test_haierproff_wifi_fallback_is_option_for_non_outdoor():
    assert HaierProffParser._should_assume_wifi_option({"Тип": "Сплит-система"}) is True
    assert HaierProffParser._should_assume_wifi_option({"Тип": "Наружный блок"}) is False


def test_haierproff_extract_specs_keeps_group_prefixed_duplicates():
    html = """
    <div class="accordion">
      <div class="collapse">
        <div class="collapse__header">Внутренний блок</div>
        <div class="collapse__content">
          <div class="spec-l__item">
            <div class="spec-l__item-label">Габаритные размеры без упаковки (Ш/Г/В), мм</div>
            <div class="spec-l__item-value">974 × 223 × 318</div>
          </div>
        </div>
      </div>
      <div class="collapse">
        <div class="collapse__header">Наружный блок</div>
        <div class="collapse__content">
          <div class="spec-l__item">
            <div class="spec-l__item-label">Габаритные размеры без упаковки (Ш/Г/В), мм</div>
            <div class="spec-l__item-value">875 × 355 × 642</div>
          </div>
        </div>
      </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")

    specs = HaierProffParser._extract_specs(soup)

    assert specs["Габаритные размеры без упаковки (Ш/Г/В), мм"] == "974 × 223 × 318"
    assert specs["Внутренний блок: Габаритные размеры без упаковки (Ш/Г/В), мм"] == "974 × 223 × 318"
    assert specs["Наружный блок: Габаритные размеры без упаковки (Ш/Г/В), мм"] == "875 × 355 × 642"


def test_haierproff_extract_manuals_from_icon_link_list():
    html = """
    <div class="icon-link-l-list">
      <a class="icon-link-l" href="/lfm_files/35/Flexis/certificate.pdf" target="_blank">
        <div class="icon-link-l__text">Сертификат соответствия</div>
      </a>
      <a class="icon-link-l" href="/lfm_files/shares/Quantum/manual.pdf" target="_blank">
        <div class="icon-link-l__text">Руководство пользователя</div>
      </a>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")

    manuals = HaierProffParser._extract_manuals(
        soup,
        "https://haierproff.ru/catalog/cond/products/sample-model",
    )

    assert manuals == [
        {
            "kind": "manual",
            "title": "Сертификат соответствия",
            "url": "https://haierproff.ru/lfm_files/35/Flexis/certificate.pdf",
            "source": "haierproff",
        },
        {
            "kind": "manual",
            "title": "Руководство пользователя",
            "url": "https://haierproff.ru/lfm_files/shares/Quantum/manual.pdf",
            "source": "haierproff",
        },
    ]
