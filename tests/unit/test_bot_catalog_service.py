from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.bot_access_service import BotAccessService
from services.bot_catalog_service import BotCatalogAccessDeniedError, BotCatalogService
from services.product_manager_service import ProductManagerService
from services.product_service import ProductService


async def test_bot_catalog_service_authorizes_staff_before_search(monkeypatch):
    search = AsyncMock(return_value=[{"id": 1}])
    monkeypatch.setattr(
        BotAccessService,
        "get_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=True)),
    )
    monkeypatch.setattr(ProductService, "search_products", search)
    session = object()

    result = await BotCatalogService.search_for_staff(
        session,
        telegram_id=123,
        query="Midea 12",
        limit=5,
    )

    assert result == [{"id": 1}]
    search.assert_awaited_once_with(session, query="Midea 12", limit=5)


async def test_bot_catalog_service_denies_non_staff_before_product_read(monkeypatch):
    search = AsyncMock()
    monkeypatch.setattr(
        BotAccessService,
        "get_context",
        AsyncMock(return_value=SimpleNamespace(is_staff=False)),
    )
    monkeypatch.setattr(ProductService, "search_products", search)

    with pytest.raises(BotCatalogAccessDeniedError, match="Staff catalog access"):
        await BotCatalogService.search_for_staff(
            object(),
            telegram_id=123,
            query="Midea",
            limit=5,
        )

    search.assert_not_awaited()


async def test_product_search_does_not_run_diagnostic_count_queries(monkeypatch):
    smart_search = AsyncMock(return_value={"items": [{"id": 1}]})
    monkeypatch.setattr(ProductManagerService, "smart_search", smart_search)
    session = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("unexpected count query")))

    result = await ProductService.search_products(session, query="Midea", limit=5)

    assert result == [{"id": 1}]
    session.execute.assert_not_awaited()
