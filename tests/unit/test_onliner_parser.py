from bs4 import BeautifulSoup

from parsers.onliner import OnlinerParser


def test_extract_spec_value_reads_boolean_check_icon():
    html = "<td><span class='i-tip'></span><!----></td>"
    cell = BeautifulSoup(html, "html.parser").find("td")

    assert OnlinerParser._extract_spec_value(cell) == "да"


def test_extract_spec_value_reads_boolean_cross_icon():
    html = "<td><span class='i-x'></span><!----></td>"
    cell = BeautifulSoup(html, "html.parser").find("td")

    assert OnlinerParser._extract_spec_value(cell) == "нет"


def test_extract_spec_value_falls_back_to_text():
    html = "<td>приобретается отдельно</td>"
    cell = BeautifulSoup(html, "html.parser").find("td")

    assert OnlinerParser._extract_spec_value(cell) == "приобретается отдельно"


def test_infer_manufacturer_uses_api_value():
    assert (
        OnlinerParser._infer_manufacturer(
            {"manufacturer": {"name": "Haier"}},
            "Кондиционер Другой Бренд",
        )
        == "Haier"
    )


def test_infer_manufacturer_falls_back_to_product_title():
    assert OnlinerParser._infer_manufacturer({}, "Кондиционер MDV MDSAG-09") == "MDV"
    assert OnlinerParser._infer_manufacturer({}, "Hisense AS-10") == "Hisense"
