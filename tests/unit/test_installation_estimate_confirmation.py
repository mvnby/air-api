from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, func, select

from models import (
    InstallationEstimate, InstallationEstimateRevision, InstallationPriceBook,
    InstallationPreviewSnapshot, Order, OrderProductLink, OrderProposal, OrderServiceLink, OrderStatus,
    Storefront, Tenant,
)
from models.tenancy import TenantScope
from schemas_installation_confirmation import ManagerInstallationAttachPayload, ManagerInstallationConfirmPayload
from schemas_installation_price_book import InstallationPreviewPayload
from schemas import ManagerOrderUpdatePayload
from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService as Confirm
from services.installation_price_book_service import InstallationPriceBookService as Book
from services.order_update.command import OrderUpdateCommandService


def _entry(mode="fixed", price="500.00"):
    return {
        "tariff_id": 1, "code": "installation.wall.2_4", "mode": mode,
        "match": {"product_kind": "complete_split_system", "indoor_type": "wall",
                  "capacity_min_kw": "2", "capacity_max_kw": "4",
                  "pipe_liquid": '1/4"', "pipe_gas": '3/8"'},
        "base_price": price, "short_name": "Монтаж", "description": "Черновое описание",
        "included_route_m": "3", "included_holes": {"diamond": "1"},
        "rules": [
            {"id": 1, "code": "route.extra_m", "rule_type": "per_meter_over_included",
             "name": "Трасса", "line_template": "{name}", "unit": "м",
             "unit_price": "10.25", "is_optional": False, "sort_order": 1},
            {"id": 2, "code": "hole.diamond.extra", "rule_type": "per_hole_manual",
             "name": "Алмазное отверстие", "line_template": "{name}", "unit": "шт",
             "unit_price": "50.00", "is_optional": False, "sort_order": 2},
        ],
    }


def _payload():
    profile = {"product_kind": "complete_split_system", "indoor_type": "wall",
               "capacity_cooling_kw": "2.5", "pipe_liquid": '1/4"', "pipe_gas": '3/8"',
               "confirmed": True}
    return InstallationPreviewPayload.model_validate({"installations": [
        {"key": "one", "typed_profile": profile, "route_length_m": "6",
         "holes_by_type": {"diamond": 2}},
    ], "expected_revision": 1})


def test_equipment_proof_uses_only_target_proposal_and_quantity():
    order = Order(tenant_id=1, storefront_id=1)
    order.product_links = [
        OrderProductLink(proposal_id=10, product_id=21, quantity=1, price=1000),
        OrderProductLink(proposal_id=11, product_id=22, quantity=2, price=1000),
    ]
    payload = InstallationPreviewPayload.model_validate({"installations": [
        {"key": "a", "product_id": 21, "route_length_m": 3, "holes_by_type": {}},
        {"key": "b", "product_id": 22, "route_length_m": 3, "holes_by_type": {}},
    ]})
    with pytest.raises(HTTPException) as error:
        Confirm._verify_equipment(order, 10, payload, [])
    assert error.value.detail["code"] == "equipment_not_in_proposal"
    order.product_links.append(OrderProductLink(proposal_id=10, product_id=22, quantity=1, price=1000))
    Confirm._verify_equipment(order, 10, payload, [])
    order.product_links[-1].is_installation_included = True
    with pytest.raises(HTTPException):
        Confirm._verify_equipment(order, 10, payload, [])
    manual = _payload()
    with pytest.raises(HTTPException) as error:
        Confirm._verify_equipment(order, 10, manual, [])
    assert error.value.detail["code"] == "service_only_verification_required"


def test_collapsed_and_detailed_projection_reconcile_discount_cent():
    snapshot = {"result": {
        "status": "fixed", "scope_ref": "scope", "subtotal": "510.25",
        "discount": "0.01", "total": "510.24", "customer_text": "Установка one: монтаж, трасса 4 м.",
        "installations": [{"installation_key": "one", "tariff_code": "installation.wall",
            "work_label": "Монтаж", "measured": [{"code": "route.length_m", "label": "Трасса",
                "unit": "м", "actual": "4", "included": "3", "extra": "1"}], "selected_extras": []}],
        "components": [
            {"code": "installation.base", "installation_key": "one", "unit": "шт",
             "quantity": "1", "unit_price": "500.00", "gross": "500.00",
             "discount": "0.01", "net": "499.99", "description": "Монтаж"},
            {"code": "route.extra_m", "installation_key": "one", "unit": "м",
             "quantity": "1", "unit_price": "10.25", "gross": "10.25",
             "discount": "0.00", "net": "10.25", "description": "Трасса"},
        ],
    }}
    saved = InstallationEstimateRevision(estimate_id=1, revision=1, price_book_id=1,
                                         price_book_revision=1, total=Decimal("510.24"), snapshot=snapshot)
    collapsed, total = Confirm._projection(saved, "collapsed")
    detailed, detailed_total = Confirm._projection(saved, "detailed")
    assert total == detailed_total == Decimal("510.24")
    assert collapsed == [("Установка one: монтаж, трасса 4 м.", Decimal("510.24"))]
    assert [price for _, price in detailed] == [Decimal("499.99"), Decimal("10.25")]
    assert sum((price for _, price in detailed), Decimal("0")) == total
    assert "фактически 4 м" in detailed[1][0]


@pytest.mark.asyncio
async def test_confirmed_revision_survives_preview_expiry_and_attach_is_exact(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'confirmed.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    scope = TenantScope(tenant_id=301, storefront_id=302)
    try:
        async with factory() as session:
            session.add(Tenant(id=301, slug="confirmed", display_name="Confirmed"))
            session.add(Storefront(id=302, tenant_id=301, slug="main", display_name="Main",
                                   status="active", is_default=True))
            book = InstallationPriceBook(tenant_id=301, revision=1, fingerprint="book-one",
                                         entries=[_entry()])
            session.add(book)
            order = Order(tenant_id=301, storefront_id=302, status=OrderStatus.NEGOTIATION)
            session.add(order)
            await session.flush()
            proposal = OrderProposal(order_id=order.id, name="Selected", is_selected=True)
            session.add(proposal)
            await session.commit()
            order_id = int(order.id)

            preview = await Book.preview(session, scope, _payload(), idempotency_key="manager-preview-key-one")
            assert preview.status == "fixed" and preview.total == Decimal("580.75")
            confirm_payload = ManagerInstallationConfirmPayload(
                preview_ref=preview.preview_ref, order_id=order.id, proposal_id=proposal.id,
                verified_service_only_keys=["one"],
            )
            confirmed = await Confirm.confirm(session, scope, confirm_payload,
                                              idempotency_key="manager-confirm-key-one", actor="manager")
            assert confirmed.value.total == Decimal("580.75")
            assert confirmed.value.revision == 1
            retry = await Confirm.confirm(session, scope, confirm_payload,
                                          idempotency_key="manager-confirm-key-one", actor="manager")
            assert retry.replayed and retry.value == confirmed.value
            assert await session.scalar(select(func.count(InstallationEstimate.id))) == 1

            attached = await Confirm.attach(session, scope, order_id=order.id, proposal_id=proposal.id,
                estimate_id=confirmed.value.estimate_id,
                payload=ManagerInstallationAttachPayload(revision=1), idempotency_key="manager-attach-key-one")
            assert attached.value.total == Decimal("580.75")
            assert len(attached.value.lines) == 1
            assert attached.value.lines[0].price == Decimal("580.75")
            repeated = await Confirm.attach(session, scope, order_id=order.id, proposal_id=proposal.id,
                estimate_id=confirmed.value.estimate_id,
                payload=ManagerInstallationAttachPayload(revision=1), idempotency_key="manager-attach-key-two")
            assert repeated.value == attached.value
            assert await session.scalar(select(func.count(OrderServiceLink.id))) == 1
            await session.refresh(order)
            assert Decimal(str(order.total_amount)) == Decimal("580.75")
            for replacement in ({"products": []}, {"services": []}):
                with pytest.raises(ValueError, match="Attached installation estimate lines are immutable"):
                        await OrderUpdateCommandService.update_order_for_manager(
                        session, order_id, ManagerOrderUpdatePayload(**replacement), tenant_scope=scope,
                    )

            snapshot = (await session.execute(select(InstallationPreviewSnapshot))).scalar_one()
            snapshot.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(snapshot)
            await session.commit()
            retained = await Confirm.get_revision(session, scope, confirmed.value.estimate_id, 1)
            assert retained.snapshot["result"]["total"] == "580.75"
            assert retained.snapshot["confirmation"]["actor"] == "manager"
            assert (await session.execute(select(InstallationEstimateRevision))).scalar_one().total == Decimal("580.75")
            with pytest.raises(HTTPException) as foreign:
                await Confirm.get_revision(session, TenantScope(tenant_id=301, storefront_id=999),
                                           confirmed.value.estimate_id, 1)
            assert foreign.value.status_code == 404
    finally:
        await engine.dispose()
