"""Exercise draft overrides against real persisted estimates and order commands."""

import copy
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select

from models import (InstallationEstimate, InstallationEstimateRevision, InstallationPriceBook,
                    Order, OrderProductLink, OrderProposal, OrderServiceLink, OrderStatus,
                    Product, Storefront, Tenant)
from models.tenancy import TenantScope
from schemas import ManagerOrderUpdatePayload, OrderProposalCreatePayload
from schemas_installation_confirmation import ManagerInstallationAttachPayload
from schemas_installation_price_book import InstallationPreviewPayload
from services.installation_estimate_confirmation_service import InstallationEstimateConfirmationService as Confirm
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service_description import service_line_document_title
from services.order_update.command import OrderUpdateCommandService as Update


@asynccontextmanager
async def _saved(tmp_path, *, legacy=False):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'commercial.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            scope = TenantScope(tenant_id=701, storefront_id=702)
            session.add(Tenant(id=701, slug="commercial", display_name="Commercial"))
            session.add(Storefront(id=702, tenant_id=701, slug="main", display_name="Main", status="active"))
            book = InstallationPriceBook(tenant_id=701, revision=1, fingerprint="commercial", entries=[])
            order = Order(tenant_id=701, storefront_id=702, status=OrderStatus.NEGOTIATION)
            product = Product(title="Equipment", slug="commercial-equipment", price=2000)
            session.add_all([book, order, product])
            await session.flush()
            proposal = OrderProposal(order_id=order.id, is_selected=True)
            session.add(proposal)
            await session.flush()
            session.add(OrderProductLink(order_id=order.id, proposal_id=proposal.id,
                                         product_id=product.id, quantity=2, price=2000, cost=1000))
            estimate = InstallationEstimate(tenant_id=701, storefront_id=702, order_id=order.id,
                proposal_id=proposal.id, confirmation_key_hash="key", confirmation_request_hash="request",
                preview_token_hash="preview")
            session.add(estimate)
            await session.flush()
            result = {"status": "fixed", "scope_ref": "scope", "subtotal": "1200.00", "discount": "0.00",
                      "total": "1200.00", "customer_text": "Исходный монтаж", "installations": [], "components": []}
            inputs = []
            for key, route in (("one", "3"), ("two", "5")):
                inputs.append({"key": key, "product_id": product.id, "route_length_m": route, "holes_by_type": {}})
                result["installations"].append({"installation_key": key, "tariff_code": "wall", "work_label": "Монтаж",
                    "short_title": "Монтаж", "included_scope": [f"Трасса {route} м"], "measured": [], "selected_extras": []})
                result["components"].append({"code": "installation.base", "installation_key": key, "unit": "шт",
                    "quantity": "1", "unit_price": "600.00", "gross": "600.00", "discount": "0.00",
                    "net": "600.00", "description": "Монтаж"})
            snapshot = {"input": {"installations": inputs}, "result": result, "commercial_projection_version": 2}
            if legacy:
                snapshot.pop("commercial_projection_version")
            revision = InstallationEstimateRevision(estimate_id=estimate.id, revision=1, price_book_id=book.id,
                price_book_revision=1, total=Decimal("1200.00"), snapshot=snapshot)
            session.add(revision)
            await session.flush()
            session.add_all(Confirm.new_revision_lines(order_id=order.id, proposal_id=proposal.id, saved=revision, mode="collapsed"))
            await session.commit()
            yield SimpleNamespace(session=session, scope=scope, order_id=int(order.id), proposal_id=int(proposal.id),
                                  revision_id=int(revision.id), estimate_id=int(estimate.id), snapshot=copy.deepcopy(snapshot), book_id=int(book.id))
    finally:
        await engine.dispose()


async def _links(case):
    return list((await case.session.execute(select(OrderServiceLink).where(
        OrderServiceLink.order_id == case.order_id, OrderServiceLink.proposal_id == case.proposal_id,
    ).order_by(OrderServiceLink.id))).scalars())


def _row(link, **changes):
    return {"link_id": link.id, "service_id": link.service_id, "title": link.title,
            "quantity": link.quantity, "price": float(link.price), "cost": float(link.cost), **changes}


async def _update(case, **fields):
    return await Update.update_order_for_manager(case.session, case.order_id,
        ManagerOrderUpdatePayload(line_proposal_id=case.proposal_id, **fields), tenant_scope=case.scope)


@pytest.mark.asyncio
async def test_edit_detaches_whole_revision_preserves_scope_and_description_patch_semantics(tmp_path):
    async with _saved(tmp_path) as case:
        from services.order_projection_service import OrderProjectionService
        projected = await OrderProjectionService.get_order_detail_for_manager(case.session, case.order_id, tenant_scope=case.scope)
        links = await _links(case)
        descriptions = {row["id"]: row["description"] for row in projected["service_lines"]}
        await _update(case, services=[_row(link, description=descriptions[link.id]) for link in links])
        assert all(link.installation_estimate_revision_id == case.revision_id for link in await _links(case))
        edited = await _update(case, services=[_row(links[0], title="Монтаж по договорённости", quantity=2, price=550, description="Трасса 5 м"), _row(links[1])])
        links = await _links(case)
        assert all(link.installation_estimate_revision_id is None and link.installation_line_index is None
                   and link.installation_projection_mode is None for link in links)
        assert (links[0].title, links[0].quantity, links[0].price, links[0].description) == ("Монтаж по договорённости", 2, Decimal("550"), "Трасса 5 м")
        assert links[1].description == descriptions[links[1].id]
        assert edited["service_lines"][0]["description"] == "Трасса 5 м"
        assert service_line_document_title(links[0]) == "Монтаж по договорённости\nТрасса 5 м"
        await _update(case, services=[_row(link) for link in links])
        assert (await _links(case))[0].description == "Трасса 5 м"
        clone = await OrderProposalCommandService.create_order_proposal(case.session, case.order_id,
            OrderProposalCreatePayload(name="Copy", duplicate_from_proposal_id=case.proposal_id), tenant_scope=case.scope)
        copied = next(proposal for proposal in clone["proposals"] if proposal["name"] == "Copy")
        assert copied["service_lines"][0]["description"] == "Трасса 5 м"
        await _update(case, services=[_row(links[0], description=None), _row(links[1])])
        assert (await _links(case))[0].description is None
        revision = await case.session.get(InstallationEstimateRevision, case.revision_id)
        assert revision.snapshot == case.snapshot and revision.total == Decimal("1200")


@pytest.mark.asyncio
async def test_partial_delete_releases_claims_and_readding_same_keys_is_explicit(tmp_path):
    async with _saved(tmp_path) as case:
        incoming = InstallationPreviewPayload.model_validate(case.snapshot["input"])
        with pytest.raises(ValueError, match="identity is already attached"):
            await Confirm.validate_attached_claims(case.session, case.order_id, case.proposal_id, incoming=incoming)
        links = await _links(case)
        await _update(case, services=[_row(links[1])])
        remaining = (await _links(case))[0]
        assert remaining.installation_estimate_revision_id is None and "Трасса 5 м" in remaining.description
        await Confirm.validate_attached_claims(case.session, case.order_id, case.proposal_id, incoming=incoming)
        attached = await Confirm.attach(case.session, case.scope, order_id=case.order_id, proposal_id=case.proposal_id,
            estimate_id=case.estimate_id, payload=ManagerInstallationAttachPayload(revision=1), idempotency_key="explicit-readd-command")
        assert len(attached.value.lines) == 2
        assert sum(link.installation_estimate_revision_id is not None for link in await _links(case)) == 2
        assert (await case.session.get(InstallationEstimateRevision, case.revision_id)).snapshot == case.snapshot


@pytest.mark.asyncio
async def test_detaching_original_does_not_detach_another_proposal_copy(tmp_path):
    async with _saved(tmp_path) as case:
        cloned = await OrderProposalCommandService.create_order_proposal(case.session, case.order_id,
            OrderProposalCreatePayload(name="Attached copy", duplicate_from_proposal_id=case.proposal_id), tenant_scope=case.scope)
        copy_id = next(proposal["id"] for proposal in cloned["proposals"] if proposal["name"] == "Attached copy")
        links = await _links(case)
        await _update(case, services=[_row(links[0], price=550), _row(links[1])])
        copied = list((await case.session.execute(select(OrderServiceLink).where(
            OrderServiceLink.proposal_id == copy_id,
        ).order_by(OrderServiceLink.id))).scalars())
        assert all(link.installation_estimate_revision_id == case.revision_id and link.price == Decimal("600") for link in copied)
        assert all(link.description and "Трасса" in link.description for link in copied)


@pytest.mark.asyncio
async def test_direct_legacy_aggregate_edit_keeps_literal_frozen_scope(tmp_path):
    async with _saved(tmp_path, legacy=True) as case:
        links = await _links(case)
        assert len(links) == 1 and links[0].price == Decimal("1200")
        updated = await _update(case, services=[_row(links[0], price=550)])
        manual = (await _links(case))[0]
        assert manual.installation_estimate_revision_id is None
        assert manual.title == "Исходный монтаж" and manual.price == Decimal("550")
        assert "Трасса 3 м" in manual.description and "Трасса 5 м" in manual.description
        assert updated["service_lines"][0]["description"] == manual.description
        assert not updated["service_lines"][0].get("installation_display_lines")
        assert (await case.session.get(InstallationEstimateRevision, case.revision_id)).snapshot == case.snapshot


@pytest.mark.asyncio
async def test_delete_equipment_and_attached_services_together_validates_final_state(tmp_path):
    async with _saved(tmp_path) as case:
        with pytest.raises(ValueError, match="exceeds the target proposal quantity"):
            await _update(case, products=[])
        result = await _update(case, products=[], services=[])
        assert result["product_lines"] == [] and result["service_lines"] == []
        assert (await case.session.get(InstallationEstimateRevision, case.revision_id)).snapshot == case.snapshot
        await _update(case, services=[{"title": "Ручной монтаж", "description": "Трасса 5 м", "quantity": 1, "price": 550}])
        assert (await _links(case))[0].description == "Трасса 5 м"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["sent", "approved"])
async def test_sent_and_approved_remain_protected(tmp_path, status):
    async with _saved(tmp_path) as case:
        proposal = await case.session.get(OrderProposal, case.proposal_id)
        proposal.status = status
        await case.session.commit()
        with pytest.raises(ValueError, match="cannot be edited"):
            await _update(case, services=[])
        assert len(await _links(case)) == 2


@pytest.mark.asyncio
async def test_foreign_and_duplicate_service_ids_and_wrong_tenant_are_rejected(tmp_path):
    async with _saved(tmp_path) as case:
        links = await _links(case)
        other = OrderProposal(order_id=case.order_id)
        case.session.add(other)
        await case.session.flush()
        foreign = OrderServiceLink(order_id=case.order_id, proposal_id=other.id, title="Другой вариант", price=100)
        case.session.add(foreign)
        await case.session.commit()
        foreign_id = int(foreign.id)
        other_id = int(other.id)
        for rows in ([_row(foreign)], [_row(links[0]), _row(links[0])]):
            with pytest.raises(ValueError, match="does not belong"):
                await _update(case, services=rows)
        assert len(await _links(case)) == 2
        result = await Update.update_order_for_manager(case.session, case.order_id,
            ManagerOrderUpdatePayload(services=[]), tenant_scope=TenantScope(tenant_id=999, storefront_id=998))
        assert result is None
        assert (await case.session.get(OrderServiceLink, foreign_id)).proposal_id == other_id
        assert len(await _links(case)) == 2
