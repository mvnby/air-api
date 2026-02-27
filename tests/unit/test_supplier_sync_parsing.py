from decimal import Decimal

from services.supplier_sync_service import (
    _extract_range_start_row,
    _normalize_currency,
    _parse_decimal,
    _parse_qty,
)
from services.supplier_availability import classify_availability


def test_parse_decimal_with_spaces_and_comma():
    assert _parse_decimal("2 670") == Decimal("2670")
    assert _parse_decimal("479,50") == Decimal("479.50")
    assert _parse_decimal(" 1\u00a0234.75 ") == Decimal("1234.75")


def test_parse_qty_and_currency_normalization():
    assert _parse_qty("10") == 10
    assert _parse_qty("10,0") == 10
    assert _parse_qty("") == 0

    assert _normalize_currency("usd") == "USD"
    assert _normalize_currency("$") == "USD"
    assert _normalize_currency("byn") == "BYN"
    assert _parse_qty("в наличии") == 1
    assert _parse_qty("в наличии 4 шт") == 4
    assert _parse_qty("ожидается поставка") == 0
    assert _parse_qty("нет в наличии") == 0


def test_availability_classification():
    assert classify_availability("в наличии") == "in_stock"
    assert classify_availability("приход июнь-июль") == "incoming"
    assert classify_availability("нет в наличии") == "out_of_stock"


def test_extract_range_start_row():
    assert _extract_range_start_row("A14:E29") == 14
    assert _extract_range_start_row("Sheet1!B26:F40") == 26
    assert _extract_range_start_row("") == 1
