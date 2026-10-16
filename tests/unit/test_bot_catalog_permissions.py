from unittest.mock import AsyncMock

import pytest

from services.bot_access_service import BotAccessContext, BotAccessService
from services.bot_api_access import BotUseCaseAccessDeniedError, require_bot_catalog_editor
from services.bot_catalog_operations_api_service import BotCatalogOperationsApiService
from services.product_service import ProductService


@pytest.mark.asyncio
async def test_telegram_manager_cannot_bypass_shared_catalog_grants(monkeypatch):
    context = BotAccessContext(telegram_id=7, is_staff=True, primary_role="manager")
    monkeypatch.setattr(BotAccessService, "get_context", AsyncMock(return_value=context))
    update = AsyncMock(return_value=True)
    delete = AsyncMock(return_value=True)
    monkeypatch.setattr(ProductService, "update_price", update)
    monkeypatch.setattr(ProductService, "delete", delete)
    with pytest.raises(BotUseCaseAccessDeniedError):
        await BotCatalogOperationsApiService.update_price(object(), telegram_id=7, product_id=4, price=2000)
    with pytest.raises(BotUseCaseAccessDeniedError):
        await BotCatalogOperationsApiService.delete_product(object(), telegram_id=7, product_id=4)
    update.assert_not_awaited()
    delete.assert_not_awaited()
    context.permissions = ("catalog.master.edit",)
    assert await BotCatalogOperationsApiService.update_price(object(), telegram_id=7, product_id=4, price=2000)
    with pytest.raises(BotUseCaseAccessDeniedError):
        await BotCatalogOperationsApiService.delete_product(object(), telegram_id=7, product_id=4)
    context.permissions = ("catalog.master.edit", "catalog.master.delete")
    assert await BotCatalogOperationsApiService.delete_product(object(), telegram_id=7, product_id=4)
    context.permissions = ()
    with pytest.raises(BotUseCaseAccessDeniedError):
        await require_bot_catalog_editor(object(), 7)


@pytest.mark.asyncio
async def test_bound_telegram_owner_keeps_access_but_inactive_owner_does_not(monkeypatch):
    context = BotAccessContext(telegram_id=7, is_staff=True, is_platform_owner=True)
    monkeypatch.setattr(BotAccessService, "get_context", AsyncMock(return_value=context))
    assert await require_bot_catalog_editor(object(), 7, deleting=True) is context
    context.is_staff = False
    with pytest.raises(BotUseCaseAccessDeniedError):
        await require_bot_catalog_editor(object(), 7, deleting=True)
