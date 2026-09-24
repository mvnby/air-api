"""Regression coverage for saved estimate money before any order write."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from crud.service_estimate import ServiceEstimateDAO
from models import Order, OrderProposal, OrderServiceLink, ServiceTariff, ServiceTariffRule
from schemas import ManagerInstallEstimateCalculatePayload, ManagerServiceEstimateOrderLinesMode
from schemas_manager_orders import ManagerOrderServiceLinePayload
from services.service_estimate_money import allocate_discount, exact_money, writable_service_money
from services.service_estimate_service import ServiceEstimateService
from services.documents.base import BaseDocumentStrategy
from services.documents.standard import GeneralDocStrategy


def _snapshot(amounts: list[str], discount: str = "0") -> SimpleNamespace:
    items = [
        SimpleNamespace(
            id=index + 1, source_type="rule", source_id=index + 1,
            service_id=None, name=f"Работа {index + 1}", short_name=f"Работа {index + 1}",
            full_description=f"Описание {index + 1}", qty=1, unit="шт",
            line_total=Decimal(amount), sort_order=index,
        )
        for index, amount in enumerate(amounts)
    ]
    subtotal = sum((Decimal(amount) for amount in amounts), Decimal("0"))
    return SimpleNamespace(
        id=42, title="Снимок сметы", tariff_id=None, tariff=None,
        calculation_payload={}, items=items, subtotal=subtotal,
        discount_amount=Decimal(discount), total=subtotal - Decimal(discount),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("amounts", "discount", "expected"),
    [
        (["600.00", "230.00"], "30.00", [578.31, 221.69]),
        (["100.40", "100.40"], "0", [100.4, 100.4]),
        (["0.05", "0.05"], "0.01", [0.04, 0.05]),
        (["0.05", "0.05"], "0.10", [0.0, 0.0]),
    ],
)
async def test_collapsed_and_detailed_saved_estimate_are_equal(
    monkeypatch, amounts, discount, expected,
):
    from core.config import settings

    monkeypatch.setattr(settings, "EXACT_SERVICE_MONEY_WRITES_ENABLED", True)
    snapshot = _snapshot(amounts, discount)

    async def get_snapshot(*_args):
        return snapshot

    monkeypatch.setattr(ServiceEstimateDAO, "get_by_id", get_snapshot)
    detailed = await ServiceEstimateService.get_estimate_order_lines(
        None, 42, mode=ManagerServiceEstimateOrderLinesMode.detailed,
    )
    collapsed = await ServiceEstimateService.get_estimate_order_lines(
        None, 42, mode=ManagerServiceEstimateOrderLinesMode.collapsed,
    )
    assert [line.price for line in detailed.services] == expected
    assert sum(Decimal(str(line.price)) for line in detailed.services) == Decimal(str(collapsed.services[0].price))
    assert Decimal(str(collapsed.services[0].price)) == snapshot.total
    assert [line.title for line in detailed.services] == [f"Работа {index + 1}" for index in range(len(amounts))]


@pytest.mark.asyncio
async def test_inconsistent_legacy_snapshot_blocks_import(monkeypatch):
    snapshot = _snapshot(["100.40", "100.40"])
    snapshot.total = Decimal("200.81")

    async def get_snapshot(*_args):
        return snapshot

    monkeypatch.setattr(ServiceEstimateDAO, "get_by_id", get_snapshot)
    with pytest.raises(HTTPException) as error:
        await ServiceEstimateService.get_estimate_order_lines(None, 42)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_fractional_import_waits_for_both_api_nodes(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "EXACT_SERVICE_MONEY_WRITES_ENABLED", False)
    snapshot = _snapshot(["100.40", "100.40"])

    async def get_snapshot(*_args):
        return snapshot

    monkeypatch.setattr(ServiceEstimateDAO, "get_by_id", get_snapshot)
    with pytest.raises(HTTPException) as error:
        await ServiceEstimateService.get_estimate_order_lines(None, 42)
    assert error.value.status_code == 409
    assert "обеих API-нод" in error.value.detail


def test_discount_allocation_and_cent_validation(monkeypatch):
    assert allocate_discount([Decimal("0.00"), Decimal("1.00")], Decimal("0.00")) == [Decimal("0.00"), Decimal("1.00")]
    with pytest.raises(ValueError):
        allocate_discount([Decimal("1.00")], Decimal("1.01"))
    with pytest.raises(ValueError):
        exact_money("1.001")
    with pytest.raises(ValidationError):
        ManagerOrderServiceLinePayload(title="Монтаж", quantity=1, price=1.001)

    from core.config import settings

    monkeypatch.setattr(settings, "EXACT_SERVICE_MONEY_WRITES_ENABLED", False)
    with pytest.raises(ValueError, match="обеих API-нод"):
        writable_service_money("1.23")
    assert writable_service_money("1.00") == Decimal("1.00")
    monkeypatch.setattr(settings, "EXACT_SERVICE_MONEY_WRITES_ENABLED", True)
    assert writable_service_money("1.23") == Decimal("1.23")


def test_order_selected_proposal_total_keeps_service_cents():
    order = Order()
    order.proposals = [
        OrderProposal(id=1, is_selected=True),
        OrderProposal(id=2, is_selected=False),
    ]
    order.product_links = []
    order.service_links = [
        OrderServiceLink(proposal_id=1, price=Decimal("100.40"), cost=Decimal("50.10"), quantity=2),
        OrderServiceLink(proposal_id=2, price=Decimal("999.99"), cost=Decimal("0.00"), quantity=1),
    ]
    order.installers = []
    order.payments = []
    order.calculate_totals()
    assert order.total_amount == 200.8
    assert order.total_cost == 100.2
    assert order.margin == 100.6


def test_fractional_route_rounds_only_after_quantity_times_price():
    tariff = ServiceTariff(id=1, selector_label="Монтаж", included_route_meters=3.0)
    rule = ServiceTariffRule(
        id=2, tariff_id=1, rule_type="per_meter_over_included", name="Трасса",
        unit_price=0.05, unit="м",
    )
    payload = ManagerInstallEstimateCalculatePayload(tariff_id=1, route_length_m=3.3)
    line = ServiceEstimateService._build_rule_line(
        rule, tariff=tariff, payload=payload, quantity=1,
        rule_input_qty=None, sort_order=1,
    )
    assert line is not None
    assert line.qty == 0.3
    assert line.line_total == 0.02


def test_document_amount_in_words_keeps_kopecks():
    assert BaseDocumentStrategy._amount_in_words(100.29) == "Сто рублей, двадцать девять копеек"


def test_general_document_footer_sums_frozen_line_cents():
    strategy = GeneralDocStrategy(None, 1)
    strategy.order = SimpleNamespace(
        product_links=[],
        service_links=[SimpleNamespace(title="Монтаж", price=Decimal("100.40"), quantity=2)],
    )

    rows = strategy._prepare_table_data()

    assert rows[0][-1] == "200.80"
    assert rows[-1][-1] == "200.80"
