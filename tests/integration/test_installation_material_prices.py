from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from models.tenancy import Tenant, TenantScope
from schemas_installation_materials import (
    InstallationMaterialCostInput,
    InstallationMaterialPriceInput,
    InstallationMaterialPriceUpdate,
)
from services.installation_material_cost_service import calculate_material_cost, list_material_prices, save_material_price


@pytest.mark.asyncio
async def test_material_price_versions_and_company_boundary(db):
    tenant = Tenant(slug="material-price-test", display_name="Material price test")
    db.add(tenant)
    await db.flush()
    own = TenantScope(tenant_id=1, storefront_id=1)
    other = TenantScope(tenant_id=tenant.id, storefront_id=3)
    payload = InstallationMaterialPriceInput(
        title="Медь", supplier="Поставщик", unit="m", pack_quantity="10",
        pack_price_byn="50.01", checked_on=date(2026, 11, 1), source_url="https://example.org/prices",
    )
    price = await save_material_price(db, own, payload)
    foreign_price = await save_material_price(db, other, payload)
    assert foreign_price.id != price.id
    result = await list_material_prices(db, other, query="медь", offset=0, limit=1)
    assert [item.id for item in result.items] == [foreign_price.id] and not result.has_more

    update = InstallationMaterialPriceUpdate(
        **{**payload.model_dump(), "pack_price_byn": "75.00"}, expected_version=price.version,
    )
    with pytest.raises(HTTPException) as hidden:
        await save_material_price(db, other, update, price_id=price.id)
    assert hidden.value.status_code == 404
    saved = await save_material_price(db, own, update, price_id=price.id)
    assert saved.version == price.version + 1
    with pytest.raises(HTTPException) as stale:
        await save_material_price(db, own, update, price_id=price.id)
    assert stale.value.status_code == 409

    old_selection = InstallationMaterialCostInput(
        items=[{"price_id": price.id, "quantity": "2.72", "expected_version": price.version}],
    )
    with pytest.raises(HTTPException) as changed_price:
        await calculate_material_cost(db, own, old_selection)
    assert changed_price.value.status_code == 409
    material_use = InstallationMaterialCostInput(
        items=[{"price_id": price.id, "quantity": "2.72", "expected_version": saved.version}],
    )
    with pytest.raises(HTTPException) as inaccessible:
        await calculate_material_cost(db, other, material_use)
    assert inaccessible.value.status_code == 404
    cost = await calculate_material_cost(db, own, material_use)
    assert cost.total_byn == Decimal("20.40")
