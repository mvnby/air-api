from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core.command_actor import CommandActor
from models import Customer, Order, OrderProductLink, OrderProposal, OrderServiceLink
from models.tenancy import TenantScope
from modules.documents.application.commercial_rows import line_rows
from schemas_connector_service_order_lines import ServiceOrderProposalInput, ServiceOrderProposalEditInput
from services.connector_service_order_lines import get_service_order_proposal, edit_service_order_proposal


async def setup_order(db):
    customer = Customer(tenant_id=1, name="Test service customer", phone="")
    db.add(customer)
    await db.flush()
    order = Order(
        tenant_id=1, storefront_id=1, customer_id=customer.id, status="negotiation", workflow_type="repair"
    )
    db.add(order)
    await db.flush()
    proposal = OrderProposal(order_id=order.id, name="Repair", status="draft", is_selected=True)
    alternate = OrderProposal(order_id=order.id, name="Alternative", status="draft")
    db.add_all([proposal, alternate])
    await db.flush()
    db.add_all(
        [
            OrderServiceLink(order_id=order.id, proposal_id=alternate.id, title="Other", price=25, quantity=1),
            OrderProductLink(
                order_id=order.id, proposal_id=proposal.id, title_snapshot="Part", price=70, quantity=1
            ),
        ]
    )
    await db.commit()
    return CommandActor(1, "test", TenantScope(1, 1), "chatgpt"), order, proposal, alternate


def edit(order, proposal, version, action, *, line_id=None, line=None):
    return ServiceOrderProposalEditInput(
        order_id=order.id,
        proposal_id=proposal.id,
        expected_version=version,
        idempotency_key="test-lines-key-0001",
        action=action,
        line_id=line_id,
        line=line,
    )


@pytest.mark.asyncio
async def test_service_edits_are_scoped_and_render_native_document(db):
    actor, order, proposal, alternate = await setup_order(db)
    query = ServiceOrderProposalInput(order_id=order.id, proposal_id=proposal.id)
    initial = await get_service_order_proposal(db, actor, query)
    assert initial.total == 70 and initial.products[0].title == "Part"
    add = edit(
        order,
        proposal,
        initial.version,
        "add",
        line={
            "title": "Ремонт",
            "description": "Компрессор включён",
            "unit": "компл.",
            "quantity": 1,
            "price": "1030.00",
        },
    )
    result = await edit_service_order_proposal(db, actor, add)
    assert result.total == Decimal("1100.00") and len(result.lines) == 1
    link = await db.get(OrderServiceLink, result.lines[0].id)
    row = line_rows([], [(link, 1)])[0]
    assert row["line.unit"] == "компл." and "Компрессор включён" in row["line.title"]
    updated = await edit_service_order_proposal(
        db,
        actor,
        edit(
            order,
            proposal,
            result.version,
            "update",
            line_id=link.id,
            line={
                "title": "Ремонт",
                "description": "Дополнено",
                "unit": "усл.",
                "quantity": 2,
                "price": "500.00",
            },
        ),
    )
    assert updated.total == 1070 and updated.lines[0].unit == "усл."
    deleted = await edit_service_order_proposal(
        db, actor, edit(order, proposal, updated.version, "delete", line_id=link.id)
    )
    assert deleted.total == 70 and not deleted.lines
    other = await get_service_order_proposal(
        db, actor, ServiceOrderProposalInput(order_id=order.id, proposal_id=alternate.id)
    )
    assert other.total == 25 and other.lines[0].title == "Other"


@pytest.mark.asyncio
async def test_stale_and_sent_proposal_are_protected(db):
    actor, order, proposal, _ = await setup_order(db)
    query = ServiceOrderProposalInput(order_id=order.id, proposal_id=proposal.id)
    initial = await get_service_order_proposal(db, actor, query)
    db.add(
        OrderServiceLink(order_id=order.id, proposal_id=proposal.id, title="Manager edit", price=10, quantity=1)
    )
    await db.flush()
    line = {"title": "Repair", "unit": "шт.", "quantity": 1, "price": 100}
    with pytest.raises(HTTPException) as exc:
        await edit_service_order_proposal(db, actor, edit(order, proposal, initial.version, "add", line=line))
    assert exc.value.status_code == 409
    proposal.status = "sent"
    await db.flush()
    current = await get_service_order_proposal(db, actor, query)
    with pytest.raises(HTTPException) as exc:
        await edit_service_order_proposal(db, actor, edit(order, proposal, current.version, "add", line=line))
    assert exc.value.status_code == 409


def test_rejects_extra_fields_and_invalid_money():
    with pytest.raises(ValidationError):
        ServiceOrderProposalEditInput(
            order_id=1,
            proposal_id=1,
            idempotency_key="test-lines-key-0001",
            expected_version="x",
            action="add",
            line={"title": "x", "unit": "шт.", "quantity": 1, "price": "1.001", "extra": True},
        )


@pytest.mark.asyncio
async def test_manager_round_trip_keeps_unit_and_description(db):
    from schemas_manager_orders import ManagerOrderUpdatePayload
    from services.order_update.command import OrderUpdateCommandService

    actor, order, proposal, _ = await setup_order(db)
    query = ServiceOrderProposalInput(order_id=order.id, proposal_id=proposal.id)
    before = await get_service_order_proposal(db, actor, query)
    result = await edit_service_order_proposal(
        db,
        actor,
        edit(
            order,
            proposal,
            before.version,
            "add",
            line={
                "title": "Ремонт",
                "description": "Замена компрессора",
                "unit": "компл.",
                "quantity": 1,
                "price": "1030",
            },
        ),
    )
    line_id = result.lines[0].id
    await db.commit()
    # Existing Manager clients omit the new field; omission must preserve it.
    payload = ManagerOrderUpdatePayload(
        line_proposal_id=proposal.id,
        services=[
            {
                "link_id": line_id,
                "proposal_id": proposal.id,
                "title": "Ремонт",
                "description": "Замена компрессора",
                "service_id": None,
                "quantity": 1,
                "price": 1030,
                "cost": 0,
            }
        ],
    )
    projected = await OrderUpdateCommandService.update_order_for_manager(
        db, order.id, payload, tenant_scope=actor.tenant_scope
    )
    line = next(p for p in projected["proposals"] if p["id"] == proposal.id)["service_lines"][0]
    assert line["unit"] == "компл." and line["description"] == "Замена компрессора"
    readback = await get_service_order_proposal(db, actor, query)
    assert readback.lines[0].unit == "компл." and readback.lines[0].description == "Замена компрессора"


@pytest.mark.asyncio
async def test_version_ignores_unrelated_order_and_proposal_edits(db):
    actor, order, proposal, alternate = await setup_order(db)
    query = ServiceOrderProposalInput(order_id=order.id, proposal_id=proposal.id)
    before = await get_service_order_proposal(db, actor, query)
    order.comment = "Unrelated note"
    alternate.name = "Other proposal updated"
    alternate.is_selected = True
    proposal.is_selected = False
    await db.flush()
    after = await get_service_order_proposal(db, actor, query)
    assert before.version == after.version


@pytest.mark.asyncio
async def test_frozen_estimate_line_is_not_a_free_service(db):
    from models import InstallationEstimate, InstallationEstimateRevision, InstallationPriceBook

    actor, order, proposal, _ = await setup_order(db)
    book = InstallationPriceBook(tenant_id=1, revision=1, fingerprint="line-freeze", entries=[])
    db.add(book)
    await db.flush()
    estimate = InstallationEstimate(
        tenant_id=1,
        storefront_id=1,
        order_id=order.id,
        proposal_id=proposal.id,
        confirmation_key_hash="line-freeze-key",
        confirmation_request_hash="line-freeze-request",
        preview_token_hash="line-freeze-preview",
    )
    db.add(estimate)
    await db.flush()
    revision = InstallationEstimateRevision(
        estimate_id=estimate.id,
        revision=1,
        price_book_id=book.id,
        price_book_revision=1,
        total=Decimal("100"),
        snapshot={},
    )
    db.add(revision)
    await db.flush()
    line = OrderServiceLink(
        order_id=order.id,
        proposal_id=proposal.id,
        title="Frozen",
        quantity=1,
        price=100,
        installation_estimate_revision_id=revision.id,
    )
    db.add(line)
    await db.flush()
    before = await get_service_order_proposal(
        db, actor, ServiceOrderProposalInput(order_id=order.id, proposal_id=proposal.id)
    )
    with pytest.raises(HTTPException) as exc:
        await edit_service_order_proposal(
            db, actor, edit(order, proposal, before.version, "delete", line_id=line.id)
        )
    assert exc.value.status_code == 409
    assert await db.get(OrderServiceLink, line.id) is not None
