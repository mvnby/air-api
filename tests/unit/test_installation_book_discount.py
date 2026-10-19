from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models.tenancy import TenantScope
from services.installation_book_discount import catalog_bundle_discounts
from services.installation_discount_service import InstallationDiscountService
from services.product_collection_catalog_access import ProductCollectionCatalogAccess


@pytest.mark.asyncio
async def test_catalog_policy_uses_visible_effective_prices_and_keeps_zero(monkeypatch):
    products = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    visible = AsyncMock(return_value={
        1: SimpleNamespace(product=products[0], price=1200),
        2: SimpleNamespace(product=products[1], price=900),
    })
    decisions = AsyncMock(return_value={
        1: SimpleNamespace(applied_discount=100), 2: SimpleNamespace(applied_discount=0),
    })
    monkeypatch.setattr(ProductCollectionCatalogAccess, 'visible_by_ids', visible)
    monkeypatch.setattr(InstallationDiscountService, 'resolve_for_products', decisions)
    scope = TenantScope(tenant_id=1, storefront_id=1, is_canonical_storefront=True)
    assert await catalog_bundle_discounts(None, scope, {1, 2, 3}) == {
        1: Decimal(100), 2: Decimal(0), 3: Decimal(0),
    }
    decisions.assert_awaited_once_with(None, products=products, effective_prices={1: 1200, 2: 900})


@pytest.mark.asyncio
async def test_partner_books_do_not_read_system_discount_policy(monkeypatch):
    visible = AsyncMock(side_effect=AssertionError('must not read system policy'))
    monkeypatch.setattr(ProductCollectionCatalogAccess, 'visible_by_ids', visible)
    scope = TenantScope(tenant_id=2, storefront_id=2, is_canonical_storefront=False)
    assert await catalog_bundle_discounts(None, scope, {1}) == {}
    visible.assert_not_awaited()
