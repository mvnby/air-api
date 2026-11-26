from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from models.installation_material import InstallationMaterialPrice
from models.tenancy import TenantScope
from schemas_installation_materials import InstallationMaterialCostInput, InstallationMaterialPriceInput
from services import installation_material_cost_service as service


@pytest.mark.asyncio
async def test_consumption_cost_uses_pack_without_rounding_unit_price(monkeypatch):
    price = InstallationMaterialPrice(
        id=5, tenant_id=17, title="Труба", supplier="Поставщик", unit="m", checked_on=date(2026, 11, 1),
        pack_quantity=Decimal("15"), pack_price_byn=Decimal("123.67"),
    )
    read = AsyncMock(return_value={5: price})
    monkeypatch.setattr(service.prices, "prices_by_id", read)
    scope = TenantScope(tenant_id=17, storefront_id=20)
    session = object()
    result = await service.calculate_material_cost(
        session, scope, InstallationMaterialCostInput(items=[{"price_id": 5, "quantity": "4.68", "expected_version": 1}]),
    )
    read.assert_awaited_once_with(session, 17, [5])
    assert result.items[0].total_byn == Decimal("38.59")
    assert result.items[0].price.pack_price_byn == Decimal("123.67")
    assert result.total_byn == Decimal("38.59")


@pytest.mark.asyncio
async def test_consumption_cost_reports_unavailable_price(monkeypatch):
    monkeypatch.setattr(service.prices, "prices_by_id", AsyncMock(return_value={}))
    with pytest.raises(HTTPException) as error:
        await service.calculate_material_cost(
            object(), TenantScope(tenant_id=17, storefront_id=20),
            InstallationMaterialCostInput(items=[{"price_id": 5, "quantity": "4.68", "expected_version": 1}]),
        )
    assert error.value.status_code == 404


def test_material_input_requires_positive_decimal_and_http_source():
    fields = dict(
        title="Труба", supplier="Поставщик", unit="m", checked_on=date(2026, 11, 1),
        pack_quantity="15", pack_price_byn="123.67",
    )
    with pytest.raises(ValidationError):
        InstallationMaterialPriceInput(**{**fields, "pack_price_byn": "0"})
    with pytest.raises(ValidationError):
        InstallationMaterialPriceInput(**fields, source_url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        InstallationMaterialCostInput(items=[{"price_id": 5, "quantity": "4.68", "expected_version": 1}] * 2)
