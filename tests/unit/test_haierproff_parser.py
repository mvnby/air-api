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

