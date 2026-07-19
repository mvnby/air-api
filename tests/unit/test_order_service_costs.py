from types import SimpleNamespace

import pytest

from models import Product
from services.order_service import OrderService
from services.product_supply_metrics_service import ProductSupplyMetricsService


@pytest.mark.asyncio
async def test_get_product_purchase_cost_uses_supply_metrics_and_cache(monkeypatch):
    calls = {"count": 0}
    product = Product(id=7, title="Cost Product", slug="cost-product", price=2500, specs={"area_m2": 25})

    async def fake_compute_for_products(_session, products):
        calls["count"] += 1
        assert len(products) == 1
        assert products[0].id == 7
        return {7: {"min_cost_byn": 1756.8}}

    monkeypatch.setattr(ProductSupplyMetricsService, "compute_for_products", fake_compute_for_products)

    cache = {}
    cost_first = await OrderService._get_product_purchase_cost(SimpleNamespace(), product, cache)
    cost_second = await OrderService._get_product_purchase_cost(SimpleNamespace(), product, cache)

    assert cost_first == 1757
    assert cost_second == 1757
    assert calls["count"] == 1
    assert cache[7] == 1757


@pytest.mark.asyncio
async def test_get_product_purchase_cost_returns_zero_without_supplier_cost(monkeypatch):
    product = Product(id=8, title="No Cost Product", slug="no-cost-product", price=1800, specs={"area_m2": 20})

    async def fake_compute_for_products(_session, _products):
        return {8: {"min_cost_byn": None}}

    monkeypatch.setattr(ProductSupplyMetricsService, "compute_for_products", fake_compute_for_products)

    cost = await OrderService._get_product_purchase_cost(SimpleNamespace(), product, {})

    assert cost == 0
