from bot_app.handlers.catalog import _choose_search_products, _is_inline_search_query
from bot_app.utils import _availability_badge


def test_inline_search_accepts_1_to_3_latin_or_digit_tokens():
    assert _is_inline_search_query("lg")
    assert _is_inline_search_query("lg 9")
    assert _is_inline_search_query("chigo black 12")
    assert _is_inline_search_query("123")


def test_inline_search_rejects_non_matching_messages():
    assert not _is_inline_search_query("привет")
    assert not _is_inline_search_query("is chigo 12 good?")
    assert not _is_inline_search_query("midea 12 inverter black")  # 4 tokens
    assert not _is_inline_search_query("lg-9")  # punctuation


def test_choose_search_products_prefers_in_stock():
    products = [
        {"id": 1, "availability_status": "out_of_stock", "vitebsk_qty": 0, "minsk_qty": 0},
        {"id": 2, "availability_status": "in_stock_now", "vitebsk_qty": 0, "minsk_qty": 0},
        {"id": 3, "availability_status": "available_2_3_days", "vitebsk_qty": 0, "minsk_qty": 1},
    ]
    selected, warning = _choose_search_products(products)
    assert [p["id"] for p in selected] == [2, 3]
    assert warning is None


def test_choose_search_products_fallback_with_warning_when_no_stock():
    products = [
        {"id": 1, "availability_status": "out_of_stock", "vitebsk_qty": 0, "minsk_qty": 0},
        {"id": 2, "availability_status": "check_availability", "vitebsk_qty": 0, "minsk_qty": 0},
    ]
    selected, warning = _choose_search_products(products)
    assert [p["id"] for p in selected] == [1, 2]
    assert warning is not None


def test_availability_badge():
    assert _availability_badge({"availability_status": "in_stock_now"}) == "✅ <b>В наличии</b>\n"
    assert _availability_badge({"availability_status": "out_of_stock"}) == "⛔ <b>Нет в наличии</b>\n"
    assert _availability_badge({"vitebsk_qty": 1}) == "✅ <b>В наличии</b>\n"
    assert _availability_badge({"title": "No supply fields"}) == ""
