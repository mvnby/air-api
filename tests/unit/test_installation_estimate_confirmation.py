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
    Product, Storefront, Tenant,
)
from models.tenancy import TenantScope
from schemas_installation_confirmation import ManagerInstallationAttachPayload, ManagerInstallationConfirmPayload
from schemas_installation_price_book import InstallationPreviewPayload
from schemas import ManagerOrderUpdatePayload, OrderProposalCreatePayload
from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService as Confirm
from services.installation_price_book_service import InstallationPriceBookService as Book
from services.order_update.command import OrderUpdateCommandService
from services.order_proposal_command_service import OrderProposalCommandService


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


def test_detailed_projection_keeps_included_work_and_selected_quantities():
    snapshot = {"result": {
        "status": "fixed", "scope_ref": "scope", "subtotal": "585.00",
        "discount": "0.00", "total": "585.00", "customer_text": "Монтаж с работами на объекте.",
        "installations": [{"installation_key": "one", "tariff_code": "installation.wall",
            "work_label": "Монтаж", "measured": [
                {"code": "route.length_m", "label": "Трасса", "unit": "м",
                 "actual": "2", "included": "3", "extra": "0"},
                {"code": "hole.diamond", "label": "Алмазные отверстия", "unit": "шт",
                 "actual": "1", "included": "1", "extra": "0"}],
            "selected_extras": [{"code": "chase.extra_m", "label": "Штробление",
                                 "unit": "м", "quantity": "3"}]}],
        "site_work": [{"code": "access.lift", "label": "Вышка", "unit": "шт", "quantity": "2"}],
        "components": [
            {"code": "installation.base", "installation_key": "one", "unit": "шт",
             "quantity": "1", "unit_price": "500.00", "gross": "500.00",
             "discount": "0.00", "net": "500.00", "description": "Монтаж"},
            {"code": "chase.extra_m", "installation_key": "one", "unit": "м",
             "quantity": "3", "unit_price": "15.00", "gross": "45.00",
             "discount": "0.00", "net": "45.00", "description": "Штробление"},
            {"code": "access.lift", "installation_key": None, "unit": "шт",
             "quantity": "2", "unit_price": "20.00", "gross": "40.00",
             "discount": "0.00", "net": "40.00", "description": "Вышка"},
        ],
    }}
    saved = InstallationEstimateRevision(estimate_id=1, revision=1, price_book_id=1,
        price_book_revision=1, total=Decimal("585.00"), snapshot=snapshot)
    detailed, total = Confirm._projection(saved, "detailed")
    assert total == Decimal("585.00")
    assert "трасса 2 м (включено 3 м)" in detailed[0][0]
    assert "алмазные отверстия 1 шт (включено 1 шт)" in detailed[0][0]
    assert "Штробление: 3 м" in detailed[1][0]
    assert "Вышка: 2 шт" in detailed[2][0]


@pytest.mark.asyncio
async def test_attached_product_claims_use_total_quantity_across_revisions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'claims.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            session.add(Tenant(id=401, slug="claims", display_name="Claims"))
            session.add(Storefront(id=402, tenant_id=401, slug="main", display_name="Main",
                                   status="active", is_default=True))
            product = Product(title="Equipment", slug="claim-equipment", price=1000)
            order = Order(tenant_id=401, storefront_id=402, status=OrderStatus.NEGOTIATION)
            session.add_all([product, order])
            await session.flush()
            proposal = OrderProposal(order_id=order.id, is_selected=True)
            session.add(proposal)
            await session.flush()
            equipment = OrderProductLink(order_id=order.id, proposal_id=proposal.id,
                                         product_id=product.id, quantity=1, price=1000)
            session.add(equipment)
            await session.flush()
            estimate = InstallationEstimate(
                tenant_id=401, storefront_id=402, order_id=order.id, proposal_id=proposal.id,
                confirmation_key_hash="claim-key", confirmation_request_hash="claim-request",
                preview_token_hash="claim-preview",
            )
            session.add(estimate)
            await session.flush()
            revision = InstallationEstimateRevision(
                estimate_id=estimate.id, revision=1, price_book_id=1,
                price_book_revision=1, total=Decimal("500"),
                snapshot={"input": {"installations": [{"key": "equipment-one",
                    "product_id": product.id, "route_length_m": "3", "holes_by_type": {}}]}},
            )
            session.add(revision)
            await session.flush()
            session.add(OrderServiceLink(order_id=order.id, proposal_id=proposal.id,
                installation_estimate_revision_id=revision.id, installation_line_index=0,
                installation_projection_mode="collapsed", title="Installation", price=500))
            await session.commit()
            order_id, proposal_id, equipment_id = int(order.id), int(proposal.id), int(equipment.id)
            incoming = InstallationPreviewPayload.model_validate({"installations": [{
                "key": "equipment-two", "product_id": product.id,
                "route_length_m": "3", "holes_by_type": {},
            }]})
            with pytest.raises(ValueError, match="exceeds the target proposal quantity"):
                await Confirm.validate_attached_claims(session, order_id, proposal_id, incoming=incoming)
            equipment.quantity = 2
            session.add(equipment)
            await session.commit()
            await Confirm.validate_attached_claims(session, order_id, proposal_id, incoming=incoming)
            with pytest.raises(ValueError, match="exceeds the target proposal quantity"):
                await OrderUpdateCommandService.update_order_for_manager(
                    session, order_id, ManagerOrderUpdatePayload(products=[]),
                    tenant_scope=TenantScope(tenant_id=401, storefront_id=402),
                )
            assert await session.scalar(select(OrderProductLink.quantity).where(
                OrderProductLink.id == equipment_id,
            )) == 2
            equipment.quantity = 0
            session.add(equipment)
            await session.commit()
            with pytest.raises(ValueError, match="exceeds the target proposal quantity"):
                await Confirm.validate_attached_claims(session, order_id, proposal_id)
    finally:
        await engine.dispose()


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
            proposal_id = int(proposal.id)

            preview = await Book.preview(session, scope, _payload(), idempotency_key="manager-preview-key-one")
            assert preview.status == "fixed" and preview.total == Decimal("580.75")
            confirm_payload = ManagerInstallationConfirmPayload(
                preview_ref=preview.preview_ref, order_id=order_id, proposal_id=proposal_id,
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

            duplicate_preview = await Book.preview(
                session, scope, _payload(), idempotency_key="manager-preview-key-two",
            )
            duplicate_confirmation = await Confirm.confirm(session, scope,
                ManagerInstallationConfirmPayload(
                    preview_ref=duplicate_preview.preview_ref, order_id=order_id,
                    proposal_id=proposal_id, verified_service_only_keys=["one"],
                ), idempotency_key="manager-confirm-key-two", actor="manager")

            attached = await Confirm.attach(session, scope, order_id=order_id, proposal_id=proposal_id,
                estimate_id=confirmed.value.estimate_id,
                payload=ManagerInstallationAttachPayload(revision=1), idempotency_key="manager-attach-key-one")
            assert attached.value.total == Decimal("580.75")
            assert len(attached.value.lines) == 1
            assert attached.value.lines[0].price == Decimal("580.75")
            repeated = await Confirm.attach(session, scope, order_id=order_id, proposal_id=proposal_id,
                estimate_id=confirmed.value.estimate_id,
                payload=ManagerInstallationAttachPayload(revision=1), idempotency_key="manager-attach-key-two")
            assert repeated.value == attached.value
            assert await session.scalar(select(func.count(OrderServiceLink.id))) == 1
            await session.refresh(order)
            assert Decimal(str(order.total_amount)) == Decimal("580.75")
            attached_line = attached.value.lines[0]
            unchanged = {"link_id": attached_line.link_id, "title": attached_line.title,
                         "quantity": 1, "price": float(attached_line.price), "cost": 0}
            await OrderUpdateCommandService.update_order_for_manager(
                session, order_id, ManagerOrderUpdatePayload(products=[], services=[unchanged]),
                tenant_scope=scope,
            )
            await OrderUpdateCommandService.update_order_for_manager(
                session, order_id, ManagerOrderUpdatePayload(services=[unchanged, {
                    "title": "Независимая услуга", "quantity": 1, "price": 25, "cost": 0,
                }]), tenant_scope=scope,
            )
            saved_lines = list((await session.execute(select(OrderServiceLink).where(
                OrderServiceLink.proposal_id == proposal_id,
            ))).scalars())
            assert len(saved_lines) == 2
            assert next(line for line in saved_lines if line.installation_estimate_revision_id).id == attached_line.link_id
            unrelated_id = next(line.id for line in saved_lines if line.installation_estimate_revision_id is None)
            await OrderUpdateCommandService.update_order_for_manager(
                session, order_id, ManagerOrderUpdatePayload(services=[unchanged, {
                    "link_id": unrelated_id, "title": "Независимая услуга", "quantity": 2,
                    "price": 30, "cost": 0,
                }]), tenant_scope=scope,
            )
            assert await session.scalar(select(func.count(OrderServiceLink.id))) == 2
            assert await session.scalar(select(OrderServiceLink.quantity).where(
                OrderServiceLink.id == unrelated_id,
            )) == 2
            with pytest.raises(ValueError, match="Attached installation estimate lines are immutable"):
                await OrderUpdateCommandService.update_order_for_manager(
                    session, order_id, ManagerOrderUpdatePayload(services=[{
                        **unchanged, "price": 1,
                    }]), tenant_scope=scope,
                )

            with pytest.raises(HTTPException) as duplicate:
                await Confirm.attach(session, scope, order_id=order_id, proposal_id=proposal_id,
                    estimate_id=duplicate_confirmation.value.estimate_id,
                    payload=ManagerInstallationAttachPayload(revision=1),
                    idempotency_key="manager-attach-key-three")
            assert duplicate.value.detail["code"] == "installation_already_attached"
            assert await session.scalar(select(func.count(OrderServiceLink.id))) == 2
            new_ref = await Book.preview(
                session, scope, _payload(), idempotency_key="manager-preview-key-three",
            )
            with pytest.raises(HTTPException) as duplicate_confirmation_error:
                await Confirm.confirm(session, scope,
                    ManagerInstallationConfirmPayload(
                        preview_ref=new_ref.preview_ref, order_id=order_id,
                        proposal_id=proposal_id, verified_service_only_keys=["one"],
                    ), idempotency_key="manager-confirm-key-three", actor="manager")
            assert duplicate_confirmation_error.value.detail["code"] == "installation_already_attached"

            independent_payload = _payload().model_copy(deep=True)
            independent_payload.installations[0].key = "two"
            independent_preview = await Book.preview(
                session, scope, independent_payload, idempotency_key="manager-preview-independent",
            )
            independent_confirmation = await Confirm.confirm(session, scope,
                ManagerInstallationConfirmPayload(
                    preview_ref=independent_preview.preview_ref, order_id=order_id,
                    proposal_id=proposal_id, verified_service_only_keys=["two"],
                ), idempotency_key="manager-confirm-independent", actor="manager")
            independent_attachment = await Confirm.attach(session, scope, order_id=order_id,
                proposal_id=proposal_id, estimate_id=independent_confirmation.value.estimate_id,
                payload=ManagerInstallationAttachPayload(revision=1),
                idempotency_key="manager-attach-independent")
            assert independent_attachment.value.total == Decimal("580.75")
            assert await session.scalar(select(func.count(OrderServiceLink.id))) == 3

            cloned = await OrderProposalCommandService.create_order_proposal(
                session, order_id, OrderProposalCreatePayload(
                    name="Independent draft", duplicate_from_proposal_id=proposal_id,
                ), tenant_scope=scope,
            )
            clone_id = next(item["id"] for item in cloned["proposals"]
                            if item["name"] == "Independent draft")
            clone_links = list((await session.execute(select(OrderServiceLink).where(
                OrderServiceLink.proposal_id == clone_id,
            ))).scalars())
            clone_attached = [link for link in clone_links if link.installation_estimate_revision_id]
            assert len(clone_attached) == 2
            clone_payload = [{"link_id": link.id, "title": link.title, "quantity": link.quantity,
                              "price": float(link.price), "cost": float(link.cost)} for link in clone_links]
            clone_payload.append({"title": "Отдельная работа", "quantity": 1, "price": 10, "cost": 0})
            await OrderUpdateCommandService.update_order_for_manager(
                session, order_id, ManagerOrderUpdatePayload(
                    line_proposal_id=clone_id, services=clone_payload,
                ), tenant_scope=scope,
            )
            assert set(link.id for link in clone_attached) == set((await session.execute(
                select(OrderServiceLink.id).where(
                    OrderServiceLink.proposal_id == clone_id,
                    OrderServiceLink.installation_estimate_revision_id.is_not(None),
                ))).scalars())

            snapshots = (await session.execute(select(InstallationPreviewSnapshot))).scalars().all()
            for snapshot in snapshots:
                snapshot.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                session.add(snapshot)
            await session.commit()
            retained = await Confirm.get_revision(session, scope, confirmed.value.estimate_id, 1)
            assert retained.snapshot["result"]["total"] == "580.75"
            assert retained.snapshot["confirmation"]["actor"] == "manager"
            assert (await session.execute(select(InstallationEstimateRevision).where(
                InstallationEstimateRevision.estimate_id == confirmed.value.estimate_id,
            ))).scalar_one().total == Decimal("580.75")
            with pytest.raises(HTTPException) as foreign:
                await Confirm.get_revision(session, TenantScope(tenant_id=301, storefront_id=999),
                                           confirmed.value.estimate_id, 1)
            assert foreign.value.status_code == 404
    finally:
        await engine.dispose()
