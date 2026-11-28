"""Exercise Telegram proposal commands against the persisted Manager order."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlmodel import select

from api_contracts.bot_order_proposal import (
    BotOrderAddEquipment, BotOrderAddInstallation, BotOrderProposals, BotOrderRemoveLine,
    BotOrderSelectProposal, BotOrderUpdateLine,
)
from core.command_actor import CommandActor
from models import (
    InstallationEstimate, InstallationEstimateRevision, InstallationPriceBook,
    Order, OrderDocument, OrderMultiSplitConfiguration, OrderProductLink, OrderProposal, OrderServiceLink, OrderStatus,
    Product, ServiceTariff, Storefront, Supplier, SupplyRequest, SupplyRequestLine, Tenant, TenantCatalogGrant, TenantOffer,
)
from models.tenancy import TenantScope
from models.leads_inbox import InboxTriageState
from services.bot_order_proposal import apply_proposal, read_proposals
from services.fx_rate_service import FxRateService
from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService
from services.order_projection_service import OrderProjectionService


pytestmark = pytest.mark.asyncio


@pytest.fixture
def actor(tenant_scope):
    return CommandActor(1, "telegram-test", tenant_scope, channel="telegram")


async def _order(db, actor, *, legacy=False):
    scope = actor.tenant_scope
    order = Order(tenant_id=scope.tenant_id, storefront_id=scope.storefront_id, status=OrderStatus.NEGOTIATION)
    db.add(order)
    await db.flush()
    if legacy:
        return order, None, None
    primary = OrderProposal(order_id=order.id, name="Основное", is_selected=True)
    alternative = OrderProposal(order_id=order.id, name="Второй вариант", sort_order=10)
    db.add_all([primary, alternative])
    await db.flush()
    return order, primary, alternative


async def _detail(db, actor, order):
    detail = await OrderProjectionService.get_order_detail_for_manager(
        db, order.id, tenant_scope=actor.tenant_scope, repair_legacy_state=False,
    )
    assert detail is not None
    return detail


async def _read(db, actor, order):
    detail = await _detail(db, actor, order)
    return BotOrderProposals.model_validate(await read_proposals(db, actor, detail))


async def _apply(db, actor, order, change):
    await apply_proposal(db, actor, order.id, change, await _detail(db, actor, order))


def _remove(proposal, line, line_kind):
    return BotOrderRemoveLine(
        kind="remove_proposal_line", proposal_id=proposal.id, line_id=line.id, line_kind=line_kind, confirmed=True,
    )


async def test_edit_one_line_preserves_alternatives_and_existing_commercial_snapshots(db, actor):
    order, first, second = await _order(db, actor)
    logistics = [{"title": "Трасса", "quantity_per_parent": 2, "unit_price": 41, "legacy": "preserve"}]
    edited = OrderProductLink(
        order_id=order.id, proposal_id=first.id, price=1000, cost=615, title_snapshot="Оборудование",
        client_description="Согласованный комплект", currency_snapshot="BYN",
        logistics_components=logistics, installation_details={"wire": 5}, installation_price=200,
    )
    custom = OrderProductLink(order_id=order.id, proposal_id=first.id, price=70, cost=10, title_snapshot="Кронштейн")
    alternative = OrderProductLink(order_id=order.id, proposal_id=second.id, price=2500, cost=1200, title_snapshot="Другая модель")
    install = OrderServiceLink(
        order_id=order.id, proposal_id=first.id, title="Монтаж", description="Трасса 3 м", unit="шт",
        quantity=2, price=Decimal("125.40"), cost=Decimal("37.20"),
    )
    db.add_all([edited, custom, alternative, install])
    await db.flush()

    before = await _read(db, actor, order)
    assert before.proposals[0].total_amount == Decimal("1320.80")
    assert before.proposals[0].product_lines[0].description == "Согласованный комплект"
    assert before.proposals[1].can_select
    for private_key in ("cost", "margin", "logistics_components", "installation_details"):
        assert private_key not in before.model_dump_json()
    with pytest.raises(HTTPException) as wrong_line:
        await _apply(db, actor, order, BotOrderUpdateLine(
            kind="update_proposal_line", proposal_id=second.id, line_kind="product", line_id=edited.id, quantity=2,
        ))
    assert wrong_line.value.status_code == 404

    await _apply(db, actor, order, BotOrderUpdateLine(
        kind="update_proposal_line", proposal_id=first.id, line_kind="product", line_id=edited.id,
        quantity=3, unit_price=Decimal("1100"),
    ))
    await _apply(db, actor, order, BotOrderUpdateLine(
        kind="update_proposal_line", proposal_id=first.id, line_kind="service", line_id=install.id,
        unit_price=Decimal("150.20"),
    ))
    updated = await _read(db, actor, order)
    assert updated.proposals[0].total_amount == Decimal("3670.40")
    assert updated.proposals[0].equipment_total == Decimal("3370.00")
    assert updated.proposals[0].services_total == Decimal("300.40")
    assert updated.proposals[1].total_amount == Decimal("2500.00")
    assert updated.proposals[0].product_lines[1] == before.proposals[0].product_lines[1]
    assert edited.logistics_components == logistics
    assert edited.installation_details == {"wire": 5}
    assert (edited.cost, edited.title_snapshot, edited.client_description, edited.installation_price) == (
        615, "Оборудование", "Согласованный комплект", 200,
    )
    assert (install.cost, install.description, install.unit) == (Decimal("37.20"), "Трасса 3 м", "шт")

    second.status = "approved"
    await db.flush()
    await _apply(db, actor, order, BotOrderSelectProposal(kind="select_proposal", proposal_id=second.id))
    detail = await _detail(db, actor, order)
    assert detail["total_amount"] == 2500
    assert detail["proposal_status"] == "approved"
    assert detail["negotiation_status"] == "awaiting_payment"
    after = await _read(db, actor, order)
    assert after.selected_proposal_id == second.id
    assert not after.proposals[1].product_lines[0].can_edit_price


async def test_add_equipment_uses_current_offer_and_preserves_target_proposal(db, monkeypatch):
    monkeypatch.setattr(FxRateService, "get_supplier_usd_byn_rate", AsyncMock(return_value=3.2))
    tenant = Tenant(slug="desk-restricted", display_name="Ограниченная витрина")
    db.add(tenant)
    await db.flush()
    sites = [Storefront(tenant_id=tenant.id, slug=slug, display_name=slug, is_default=index == 0)
             for index, slug in enumerate(("desk", "other"))]
    db.add_all(sites)
    await db.flush()
    grants = [
        TenantCatalogGrant(tenant_id=tenant.id, storefront_id=site.id, status="active",
                           created_by_username="test", updated_by_username="test")
        for site in sites
    ]
    products = [
        Product(title=title, slug=title, price=1000, product_kind="complete_split_system", is_published=True)
        for title in ("visible", "foreign", "ungranted", "disabled", "zero-price", "new-price")
    ]
    db.add_all([*grants, *products])
    await db.flush()
    for index, (product, price) in enumerate(zip(products, (1450, 1450, 1450, 1450, 0, 1500))):
        site_index = int(index == 1)
        db.add(TenantOffer(
            tenant_id=tenant.id, storefront_id=sites[site_index].id, product_id=product.id,
            catalog_grant_id=None if index == 2 else grants[site_index].id, price=price,
            status="disabled" if index == 3 else "active", is_published=True,
            created_by_username="test", updated_by_username="test",
        ))
    actor = CommandActor(1, "telegram-test", TenantScope(tenant.id, sites[0].id), channel="telegram")
    order, first, second = await _order(db, actor)
    foreign_scope = replace(actor.tenant_scope, storefront_id=sites[1].id)
    assert await OrderProjectionService.get_order_detail_for_manager(
        db, order.id, tenant_scope=foreign_scope, repair_legacy_state=False,
    ) is None
    db.add_all([
        OrderProductLink(order_id=order.id, proposal_id=first.id, product_id=products[0].id, price=1122, cost=110),
        OrderProductLink(order_id=order.id, proposal_id=second.id, title_snapshot="Кронштейн", price=18, cost=10),
    ])
    await db.flush()

    def attach(*items):
        return BotOrderAddEquipment(
            kind="add_equipment", proposal_id=second.id,
            items=[{"product_id": product.id, "quantity": 2, "expected_unit_price_byn": 1450} for product in items],
        )

    for hidden in products[1:-1]:
        with pytest.raises(HTTPException) as ineligible:
            await _apply(db, actor, order, attach(products[0], hidden))
        assert ineligible.value.status_code == 422
    with pytest.raises(HTTPException) as stale:
        await _apply(db, actor, order, attach(products[0], products[-1]))
    assert stale.value.status_code == 409
    assert len((await _read(db, actor, order)).proposals[1].product_lines) == 1

    # A real storefront price still applies when equipment is available to order.
    await _apply(db, actor, order, attach(products[0]))
    result = await _read(db, actor, order)
    assert result.selected_proposal_id == first.id
    assert result.proposals[0].total_amount == Decimal("1122.00")
    assert result.proposals[1].total_amount == Decimal("2918.00")
    added = result.proposals[1].product_lines[1]
    assert (added.product_id, added.unit_price, added.quantity, added.title) == (
        products[0].id, Decimal("1450.00"), 2, "visible",
    )
    with pytest.raises(HTTPException) as duplicate:
        await _apply(db, actor, order, attach(products[0]))
    assert duplicate.value.status_code == 409


async def test_legacy_order_read_does_not_repair_but_first_explicit_edit_preserves_existing_lines(db, actor):
    order, _, _ = await _order(db, actor, legacy=True)
    old_product = OrderProductLink(order_id=order.id, title_snapshot="Legacy Product", price=550, cost=335)
    old_service = OrderServiceLink(order_id=order.id, title="Legacy Service", price=Decimal("113.45"), quantity=2)
    db.add_all([old_product, old_service])
    await db.flush()
    before = (await _read(db, actor, order)).proposals[0]
    assert before.id is None and before.is_selected and before.total_amount == Decimal("776.90")
    assert not (await db.execute(select(OrderProposal).where(OrderProposal.order_id == order.id))).scalars().all()

    await _apply(db, actor, order, BotOrderUpdateLine(
        kind="update_proposal_line", proposal_id=None, line_kind="product", line_id=old_product.id, quantity=2,
    ))
    after = (await _read(db, actor, order)).proposals[0]
    assert after.id is not None and after.is_selected and after.total_amount == Decimal("1326.90")
    assert after.product_lines[0].id == old_product.id
    assert after.service_lines[0] == before.service_lines[0]
    assert (await _detail(db, actor, order))["total_amount"] == 1326.9


@pytest.mark.parametrize("projection_version", [1, 2])
async def test_published_installation_replaces_legacy_options_and_freezes_saved_estimates(db, actor, projection_version):
    order, first, _ = await _order(db, actor)
    old_tariff = ServiceTariff(short_name="Старый монтаж", selector_label="Старый монтаж", base_price=410)
    db.add(old_tariff)
    await db.flush()
    initial = (await _read(db, actor, order)).proposals[0].installation_options[0]
    assert initial.id == f"tariff:{old_tariff.id}:410"
    book = InstallationPriceBook(
        tenant_id=actor.tenant_scope.tenant_id, revision=1, fingerprint="telegram-book",
        entries=[{
            "code": "wall", "mode": "fixed", "match": {"indoor_type": "wall", "match_strategy": "type_only"},
            "base_price": "435.60", "included_route_m": "3", "included_holes": {},
        }],
    )
    db.add(book)
    await db.flush()
    product = Product(title="Кондиционер для замера", slug="desk-claim", price=800)
    unrelated = Product(title="Другая позиция", slug="desk-other", price=400)
    db.add_all([product, unrelated])
    await db.flush()
    measured_equipment = OrderProductLink(order_id=order.id, proposal_id=first.id, product_id=product.id, price=800)
    other_equipment = OrderProductLink(order_id=order.id, proposal_id=first.id, product_id=unrelated.id, price=400)
    db.add_all([measured_equipment, other_equipment])
    estimate = InstallationEstimate(
        tenant_id=actor.tenant_scope.tenant_id, storefront_id=actor.tenant_scope.storefront_id, order_id=order.id,
        proposal_id=first.id, confirmation_key_hash="desk-key", confirmation_request_hash="desk-request",
        preview_token_hash="desk-preview",
    )
    db.add(estimate)
    await db.flush()
    snapshot = {
        "input": {"installations": [{
            "key": "existing", "product_id": product.id,
            "route_length_m": "3", "holes_by_type": {},
        }]},
        "result": {
            "status": "fixed", "scope_ref": "desk", "subtotal": "300.00", "discount": "0.00", "total": "300.00",
            "customer_text": "Монтаж по смете",
            "installations": [{"installation_key": "existing", "tariff_code": "wall", "work_label": "Монтаж",
                               "short_title": "Монтаж", "included_scope": [], "measured": [], "selected_extras": []}],
            "components": [{"code": "installation.base", "installation_key": "existing", "unit": "шт", "quantity": "1",
                            "unit_price": "300.00", "gross": "300.00", "discount": "0.00", "net": "300.00",
                            "description": "Монтаж"}],
        },
        "commercial_projection_version": projection_version,
    }
    revision = InstallationEstimateRevision(
        estimate_id=estimate.id, revision=1, price_book_id=book.id, price_book_revision=1,
        total=Decimal("300"), snapshot=snapshot,
    )
    db.add(revision)
    await db.flush()
    frozen = InstallationEstimateConfirmationService.new_revision_lines(
        order_id=order.id, proposal_id=first.id, saved=revision, mode="collapsed",
    )[0]
    db.add(frozen)
    await db.flush()

    before = (await _read(db, actor, order)).proposals[0]
    (standard,) = before.installation_options
    assert (standard.id, standard.unit_price) == ("standard:1:wall", Decimal("435.60"))
    assert not before.service_lines[0].can_edit_quantity and not before.service_lines[0].can_edit_price
    assert not before.service_lines[0].can_remove
    assert not before.product_lines[0].can_remove and before.product_lines[1].can_remove
    for protected, line_kind in ((frozen, "service"), (measured_equipment, "product")):
        with pytest.raises(HTTPException) as error:
            await _apply(db, actor, order, _remove(first, protected, line_kind))
        assert error.value.status_code == 409
    await _apply(db, actor, order, _remove(first, other_equipment, "product"))
    if projection_version == 1:
        (display_line,) = before.service_lines[0].display_lines
        assert (display_line.title, display_line.line_total) == ("Монтаж", Decimal("300.00"))
    with pytest.raises(HTTPException) as fixed:
        await _apply(db, actor, order, BotOrderUpdateLine(
            kind="update_proposal_line", proposal_id=first.id, line_kind="service", line_id=frozen.id, unit_price=500,
        ))
    assert fixed.value.status_code == 409
    with pytest.raises(HTTPException) as stale:
        await _apply(db, actor, order, BotOrderAddInstallation(
            kind="add_installation", proposal_id=first.id, option_id=initial.id, quantity=1,
        ))
    assert stale.value.status_code == 409
    await _apply(db, actor, order, BotOrderAddInstallation(
        kind="add_installation", proposal_id=first.id, option_id=standard.id, quantity=2,
    ))
    after = (await _read(db, actor, order)).proposals[0]
    assert after.service_lines[0] == before.service_lines[0]
    assert after.services_total == Decimal("1171.20")
    assert (after.service_lines[1].title, after.service_lines[1].description) == (standard.title, standard.description)
    assert after.total_amount == Decimal("1971.20")
    assert revision.snapshot == snapshot


async def test_offer_locks_its_lines_and_issued_order_contract_locks_proposal_selection(db, actor):
    order, first, second = await _order(db, actor)
    issued_offer_line = OrderProductLink(order_id=order.id, proposal_id=first.id, price=125)
    alternative_line = OrderServiceLink(order_id=order.id, proposal_id=second.id, title="Монтаж", price=200)
    db.add_all([
        issued_offer_line, alternative_line,
        OrderDocument(order_id=order.id, proposal_id=first.id, doc_type="offer", number="KP-1", google_file_id="legacy-offer"),
    ])
    await db.flush()
    before = await _read(db, actor, order)
    assert not before.proposals[0].can_add_equipment
    assert not before.proposals[0].product_lines[0].can_remove
    assert before.proposals[1].can_add_equipment and before.proposals[1].can_select
    assert before.proposals[1].service_lines[0].can_remove
    demo = replace(actor, tenant_scope=replace(actor.tenant_scope, demo_read_only=True))
    assert not (await _read(db, demo, order)).proposals[1].can_select

    db.add(OrderDocument(order_id=order.id, doc_type="b2c_supply_installation_act", number="А-1"))
    await db.flush()
    after = await _read(db, actor, order)
    assert not after.proposals[1].can_add_equipment and not after.proposals[1].can_select
    assert not after.proposals[1].service_lines[0].can_remove
    with pytest.raises(HTTPException) as locked:
        await _apply(db, actor, order, BotOrderSelectProposal(kind="select_proposal", proposal_id=second.id))
    assert locked.value.status_code == 409 and first.is_selected
    with pytest.raises(HTTPException) as protected:
        await _apply(db, actor, order, _remove(second, alternative_line, "service"))
    assert protected.value.status_code == 409


async def test_archived_inbox_order_is_locked_and_waiting_alone_keeps_its_draft_editable(db, actor):
    order, first, second = await _order(db, actor)
    order.is_on_hold = True
    await db.flush()
    waiting = await _read(db, actor, order)
    assert waiting.proposals[1].can_select
    await _apply(db, actor, order, BotOrderSelectProposal(kind="select_proposal", proposal_id=second.id))
    assert (await _detail(db, actor, order))["is_on_hold"]
    db.add(InboxTriageState(
        entity_kind="order", entity_id=order.id, order_id=order.id, tenant_id=order.tenant_id,
        storefront_id=order.storefront_id, outcome="refusal", archived_at=datetime.now(timezone.utc),
    ))
    await db.flush()
    archived = await _read(db, actor, order)
    assert not any(item.can_select or item.can_add_equipment for item in archived.proposals)
    with pytest.raises(HTTPException) as locked:
        await _apply(db, actor, order, BotOrderSelectProposal(kind="select_proposal", proposal_id=first.id))
    assert locked.value.status_code == 409


async def test_remove_exact_draft_product_and_service_only_with_explicit_confirmation(db, actor):
    order, first, second = await _order(db, actor)
    other, other_proposal, _ = await _order(db, actor)
    good = OrderProductLink(order_id=order.id, proposal_id=first.id, title_snapshot="Основное", price=1200)
    extra = OrderProductLink(order_id=order.id, proposal_id=first.id, title_snapshot="Лишнее", price=950)
    installation = OrderServiceLink(
        order_id=order.id, proposal_id=first.id, title="Монтаж", quantity=2, price=Decimal("125.10"),
    )
    alternative = OrderProductLink(order_id=order.id, proposal_id=second.id, title_snapshot="Вариант", price=945)
    foreign = OrderProductLink(order_id=other.id, proposal_id=other_proposal.id, title_snapshot="Другой заказ", price=830)
    db.add_all([good, extra, installation, alternative, foreign])
    await db.flush()

    expected = {
        "kind": "remove_proposal_line", "proposal_id": first.id, "line_id": extra.id, "line_kind": "product",
    }
    for invalid_confirmation in ({}, {"confirmed": False}, {"confirmed": 1}, {"confirmed": "true"}):
        with pytest.raises(ValidationError):
            BotOrderRemoveLine.model_validate(expected | invalid_confirmation)
    for unrelated in (alternative, foreign):
        with pytest.raises(HTTPException) as missing:
            await _apply(db, actor, order, _remove(first, unrelated, "product"))
        assert missing.value.status_code == 404
    first.status = "ready_to_send"
    await db.flush()
    ready = (await _read(db, actor, order)).proposals[0]
    assert ready.product_lines[1].can_edit_price and not ready.product_lines[1].can_remove
    assert ready.total_amount == Decimal("2400.20")
    with pytest.raises(HTTPException) as locked:
        await _apply(db, actor, order, _remove(first, extra, "product"))
    assert locked.value.status_code == 409

    first.status = "draft"
    await db.flush()
    await _apply(db, actor, order, _remove(first, extra, "product"))
    updated = (await _read(db, actor, order)).proposals[0]
    assert [line.id for line in updated.product_lines] == [good.id]
    assert updated.service_lines[0].id == installation.id and updated.service_lines[0].can_remove
    assert updated.total_amount == Decimal("1450.20")
    await _apply(db, actor, order, _remove(first, installation, "service"))
    after = await _read(db, actor, order)
    assert after.proposals[0].total_amount == Decimal("1200.00") and not after.proposals[0].service_lines
    assert after.proposals[1].product_lines[0].id == alternative.id
    assert (await _detail(db, actor, order))["total_amount"] == 1200
    assert await db.get(OrderProductLink, foreign.id) is foreign


async def test_removal_preserves_supplier_reserve_and_multisplit_components(db, actor):
    order, first, second = await _order(db, actor)
    product = Product(title="Модель со снабжением", slug="desk-supplier", price=950)
    supplier = Supplier(name="Поставщик", code="desk-supplier")
    db.add_all([product, supplier])
    await db.flush()
    reserved = OrderProductLink(order_id=order.id, proposal_id=first.id, product_id=product.id, price=950)
    unrelated = OrderProductLink(order_id=order.id, proposal_id=first.id, title_snapshot="Кронштейн", price=100)
    component = OrderProductLink(order_id=order.id, proposal_id=second.id, product_id=product.id, price=1220)
    supply = SupplyRequest(supplier_id=supplier.id, intent="reserve")
    db.add_all([reserved, unrelated, component, supply])
    await db.flush()
    supply_line = SupplyRequestLine(
        request_id=supply.id, order_product_link_id=reserved.id, source_type="order_line", product_id=product.id,
        title_snapshot=product.title, status="reserved",
    )
    db.add_all([
        supply_line,
        OrderMultiSplitConfiguration(
            order_id=order.id, proposal_id=second.id,
            component_snapshot=[{"product_id": product.id, "quantity": 1}],
        ),
    ])
    await db.flush()

    state = await _read(db, actor, order)
    reserve_row, other_row = state.proposals[0].product_lines
    assert not reserve_row.can_remove and not reserve_row.can_edit_quantity and reserve_row.can_edit_price
    assert other_row.can_remove
    assert not state.proposals[1].product_lines[0].can_remove
    for proposal, protected in ((first, reserved), (second, component)):
        with pytest.raises(HTTPException) as conflict:
            await _apply(db, actor, order, _remove(proposal, protected, "product"))
        assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as conflict:
        await _apply(db, actor, order, BotOrderUpdateLine(
            kind="update_proposal_line", proposal_id=first.id, line_kind="product", line_id=reserved.id, quantity=2,
        ))
    assert conflict.value.status_code == 409
    order.equipment_status = "reserved"
    await db.flush()
    assert not (await _read(db, actor, order)).proposals[0].product_lines[1].can_remove
    with pytest.raises(HTTPException) as conflict:
        await _apply(db, actor, order, _remove(first, unrelated, "product"))
    assert conflict.value.status_code == 409
    order.equipment_status = "pending"
    await db.flush()
    await _apply(db, actor, order, _remove(first, unrelated, "product"))
    assert (await _read(db, actor, order)).proposals[0].total_amount == Decimal("950.00")
    retained = await db.get(SupplyRequestLine, supply_line.id, populate_existing=True)
    assert retained.order_product_link_id == reserved.id and retained.status == "reserved"
