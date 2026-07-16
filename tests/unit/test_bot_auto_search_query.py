from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.dispatcher.event.bases import SkipHandler

from bot_app.handlers import catalog as catalog_handler
from api_contracts.bot import (
    BotCatalogProductLookupResponse,
    BotCatalogProductResponse,
    BotCatalogSearchResponse,
)
from bot_app.access import BotAccessContext
from bot_app.api_gateway import BotApiUnavailableError
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
    assert not _is_inline_search_query("m" * 101)


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


@pytest.mark.asyncio
async def test_auto_search_skips_non_search_text(monkeypatch):
    staff_check = AsyncMock(return_value=True)
    monkeypatch.setattr(catalog_handler, "_is_staff_user", staff_check)
    message = SimpleNamespace(text="УНП 392053942\nР/с BY83 BPSB 3012 3542 9501 1933 0000", from_user=SimpleNamespace(id=5))

    with pytest.raises(SkipHandler):
        await catalog_handler.auto_search_process(message)

    staff_check.assert_not_called()


@pytest.mark.asyncio
async def test_auto_search_uses_internal_api_gateway(monkeypatch):
    gateway = SimpleNamespace(
        search_catalog=AsyncMock(
            return_value=BotCatalogSearchResponse(
                items=[
                    BotCatalogProductResponse(
                        id=42,
                        title="Midea 12",
                        slug="midea-12",
                        price=3200,
                        area=35,
                    )
                ]
            )
        )
    )
    render = AsyncMock()
    monkeypatch.setattr(
        catalog_handler,
        "_get_access_context",
        AsyncMock(return_value=BotAccessContext(telegram_id=5, is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(catalog_handler, "get_bot_api_gateway", lambda: gateway)
    monkeypatch.setattr(catalog_handler, "_render_search_results", render)
    message = SimpleNamespace(text="Midea 12", from_user=SimpleNamespace(id=5))

    await catalog_handler.auto_search_process(message)

    gateway.search_catalog.assert_awaited_once_with(
        telegram_id=5,
        query="Midea 12",
        limit=5,
    )
    products = render.await_args.args[2]
    assert products == [
        {
            "id": 42,
            "title": "Midea 12",
            "slug": "midea-12",
            "description": "",
            "price": 3200,
            "area": 35,
            "main_image": None,
            "categories": [],
            "vitebsk_qty": 0,
            "minsk_qty": 0,
            "availability_status": "out_of_stock",
        }
    ]
    assert render.await_args.kwargs == {}


@pytest.mark.asyncio
async def test_explicit_search_clears_fsm_when_catalog_api_is_unavailable(monkeypatch):
    gateway = SimpleNamespace(
        search_catalog=AsyncMock(side_effect=BotApiUnavailableError("offline"))
    )
    monkeypatch.setattr(
        catalog_handler,
        "_get_access_context",
        AsyncMock(return_value=BotAccessContext(telegram_id=5, is_staff=True)),
    )
    monkeypatch.setattr(catalog_handler, "get_bot_api_gateway", lambda: gateway)
    state = SimpleNamespace(clear=AsyncMock())
    message = SimpleNamespace(text="Midea 12", from_user=SimpleNamespace(id=5))

    with pytest.raises(BotApiUnavailableError, match="offline"):
        await catalog_handler.search_process(message, state)

    state.clear.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_search_details_renders_product_from_internal_api(monkeypatch):
    product = BotCatalogProductResponse(
        id=42,
        title="Midea 12",
        slug="midea-12",
        description="Тихий инвертор",
        price=3200,
        area=35,
        categories=["Настенные"],
        minsk_qty=2,
        availability_status="available_2_3_days",
    )
    gateway = SimpleNamespace(
        get_catalog_product=AsyncMock(
            return_value=BotCatalogProductLookupResponse(product=product)
        )
    )
    send_card = AsyncMock()
    monkeypatch.setattr(
        catalog_handler,
        "_get_access_context",
        AsyncMock(return_value=BotAccessContext(telegram_id=5, is_staff=True, is_manager=True)),
    )
    monkeypatch.setattr(catalog_handler, "get_bot_api_gateway", lambda: gateway)
    monkeypatch.setattr(catalog_handler, "send_product_card", send_card)
    callback = SimpleNamespace(
        data="search_details_42",
        from_user=SimpleNamespace(id=5),
        answer=AsyncMock(),
    )

    await catalog_handler.search_details(callback)

    gateway.get_catalog_product.assert_awaited_once_with(telegram_id=5, product_id=42)
    rendered = send_card.await_args.args[1]
    assert rendered["description"] == "Тихий инвертор"
    assert rendered["categories"] == ["Настенные"]
    assert rendered["minsk_qty"] == 2
    assert send_card.await_args.args[2] is False
    callback.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_product_client_text_uses_internal_api_detail(monkeypatch):
    product = BotCatalogProductResponse(
        id=42,
        title="Midea 12",
        slug="midea-12",
        price=3200,
        minsk_qty=2,
        availability_status="available_2_3_days",
    )
    gateway = SimpleNamespace(
        get_catalog_product=AsyncMock(
            return_value=BotCatalogProductLookupResponse(product=product)
        )
    )
    monkeypatch.setattr(
        catalog_handler,
        "_get_access_context",
        AsyncMock(return_value=BotAccessContext(telegram_id=5, is_staff=True)),
    )
    monkeypatch.setattr(catalog_handler, "get_bot_api_gateway", lambda: gateway)
    monkeypatch.setattr(
        "bot_app.catalog_presenter.settings",
        SimpleNamespace(PUBLIC_SITE_URL="https://example.test"),
    )
    message = SimpleNamespace(answer=AsyncMock())
    callback = SimpleNamespace(
        data="product_client_text_42",
        from_user=SimpleNamespace(id=5),
        message=message,
        answer=AsyncMock(),
    )

    await catalog_handler.product_client_text(callback)

    gateway.get_catalog_product.assert_awaited_once_with(telegram_id=5, product_id=42)
    message.answer.assert_awaited_once_with(
        "Midea 12\n"
        "Цена: 3200 руб.\n"
        "в наличии в Минске, срок поставки 2-4 дня\n"
        "https://example.test/product/midea-12/"
    )
    callback.answer.assert_awaited_once_with("Можно переслать клиенту")
