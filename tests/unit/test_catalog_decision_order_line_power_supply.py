from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.documents.application.commercial_rows import line_rows
from services.catalog_decision_order_lines import CatalogDecisionOrderLineService
from services.order_product_line_service import OrderProductLineService


@pytest.mark.asyncio
@pytest.mark.parametrize("existing,expected", [
    (None, "питание: 380-415 В, 3 ф."),
    ("Ручное описание", "Ручное описание"),
])
async def test_catalog_replace_fills_power_without_overwriting_manual_description(monkeypatch, existing, expected):
    link = SimpleNamespace(product_id=10, client_description=existing)
    session = MagicMock(flush=AsyncMock(), execute=AsyncMock())
    session.execute.return_value = MagicMock()
    session.execute.return_value.scalars.return_value.all.return_value = [link]
    monkeypatch.setattr(OrderProductLineService, "reconcile", AsyncMock())
    snapshot = SimpleNamespace(
        product=SimpleNamespace(title="Кассетный блок", product_kind="complete_split_system",
            specs={"power_supply": "380-415/50/3"}),
        retail_price_byn=5000, purchase_cost_byn=4000,
    )
    await CatalogDecisionOrderLineService.replace(session,
        order_id=1, proposal_id=2, product_ids=[10], snapshots={10: snapshot})
    assert link.client_description == expected
    assert link.title_snapshot == "Кассетный блок"


@pytest.mark.asyncio
async def test_catalog_append_carries_stated_power_into_native_document_rows():
    session = MagicMock(flush=AsyncMock())
    snapshot = SimpleNamespace(
        product=SimpleNamespace(title="Кассетная система", product_kind="complete_split_system",
            specs={"power_supply_outdoor": "380-415/50/3", "power_supply_indoor": "220-240/50/1",
                "power_supply_location": "наружный блок"}),
        retail_price_byn=5000, purchase_cost_byn=4000,
    )
    await CatalogDecisionOrderLineService.append(session,
        order_id=1, proposal_id=2, product_ids=[10], snapshots={10: snapshot}, quantities={10: 2})
    link = session.add.call_args.args[0]
    rows = line_rows([link], [])
    assert rows[0]["line.title"] == (
        "Кассетная система\nпараметры питания внутреннего блока: 220-240 В, 1 ф.; "
        "параметры питания наружного блока: 380-415 В, 3 ф.; "
        "подключение питания: к наружному блоку"
    )
    assert rows[0]["line.quantity"] == "2"
    assert rows[0]["line.amount"] == "10000.00"
