"""Real Manager creation/qualification stays atomic and scoped through MCP."""

import pytest
from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import select

from core.command_actor import CommandActor
from models import (
    Customer,
    CustomerBranch,
    Lead,
    Order,
    OrderProductLink,
    OrderProposal,
    OrderServiceLink,
    StaffUser,
)
from models.tenancy import Storefront, Tenant, TenantMembership, TenantScope
from schemas_connector_service_order_create import ServiceOrderCreateInput
from services.command_transaction import command_transaction
from services.connector_service_order_create import create_service_order
from services.lead_service import LeadVersionConflict


async def setup(db):
    user = StaffUser(
        display_name="Service manager",
        username="service-creator",
        primary_role="admin",
        roles=["admin"],
    )
    customer = Customer(tenant_id=1, name="Existing repair customer", phone="")
    db.add_all([user, customer])
    await db.flush()
    membership = TenantMembership(tenant_id=1, staff_user_id=user.id, role="admin")
    db.add(membership)
    await db.commit()
    actor = CommandActor(user.id, user.username, TenantScope(1, 1), "chatgpt")
    data = ServiceOrderCreateInput(
        customer_id=customer.id,
        workflow_type="repair",
        request_text="Ремонт Remeza RFDA 141; компрессор в составе комплексной услуги.",
        idempotency_key="service-order-create-test-0001",
    )
    return actor, data, membership


async def count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
async def test_service_order_creates_negotiation_existing_customer_and_editable_proposal(
    db,
):
    actor, data, _ = await setup(db)
    result = await create_service_order(db, actor, data)
    order = await db.get(Order, result.order_id)
    proposal = await db.get(OrderProposal, result.proposal_id)
    assert result.status == "negotiation" and result.proposal_status == "draft"
    assert order.customer_id == data.customer_id
    assert order.responsible_staff_user_id == actor.staff_user_id
    assert order.comment == data.request_text and order.workflow_type == "repair"
    assert order.tenant_id == 1 and order.storefront_id == 1
    assert proposal.order_id == order.id and proposal.is_selected
    assert await count(db, Customer) == 1
    assert await count(db, OrderProposal) == 1
    assert await count(db, OrderProductLink) == await count(db, OrderServiceLink) == 0
    assert f"orderId={order.id}" in result.manager_url
    assert f"proposalId={proposal.id}" in result.proposal_manager_url


@pytest.mark.asyncio
async def test_service_order_qualifies_incoming_preserving_source_and_contact(db):
    actor, data, _ = await setup(db)
    lead = Lead(tenant_id=1, storefront_id=1, request_text="Исходный текст ремонта", phone="")
    db.add(lead)
    await db.commit()
    data.incoming_id, data.expected_incoming_version = lead.id, lead.version
    result = await create_service_order(db, actor, data)
    await db.refresh(lead)
    order = await db.get(Order, result.order_id)
    assert lead.converted_order_id == order.id
    assert lead.request_text == "Исходный текст ремонта"
    assert order.comment == f"Исходный текст ремонта\n\n{data.request_text}"
    assert result.incoming_version == lead.version
    assert await count(db, Customer) == 1


@pytest.mark.asyncio
async def test_service_order_stale_incoming_and_existing_conversion_do_not_duplicate(
    db,
):
    actor, data, _ = await setup(db)
    lead = Lead(tenant_id=1, storefront_id=1, request_text="Repair", phone="", version=2)
    db.add(lead)
    await db.commit()
    data.incoming_id, data.expected_incoming_version = lead.id, 1
    with pytest.raises(LeadVersionConflict):
        await create_service_order(db, actor, data)
    assert await count(db, Order) == 0
    data.expected_incoming_version = 2
    result = await create_service_order(db, actor, data)
    data.expected_incoming_version = result.incoming_version
    with pytest.raises(HTTPException) as exc:
        await create_service_order(db, actor, data)
    assert exc.value.status_code == 409
    assert await count(db, Order) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["customer", "branch", "incoming", "storefront"])
async def test_service_order_rejects_foreign_bindings_without_writes(db, resource):
    actor, data, _ = await setup(db)
    db.add(Tenant(id=2, slug="foreign-service", display_name="Foreign"))
    await db.flush()
    db.add_all(
        [
            Storefront(id=2, tenant_id=2, slug="main", display_name="Foreign"),
            Storefront(id=3, tenant_id=1, slug="other", display_name="Other"),
        ]
    )
    foreign = Customer(tenant_id=2, name="Foreign", phone="")
    db.add(foreign)
    await db.flush()
    branch = CustomerBranch(customer_id=foreign.id, name="Foreign site", delivery_address="Test site")
    lead = Lead(
        tenant_id=2 if resource != "storefront" else 1,
        storefront_id=2 if resource != "storefront" else 3,
        request_text="Foreign",
        phone="",
    )
    db.add_all([branch, lead])
    await db.commit()
    if resource == "customer":
        data.customer_id = foreign.id
    elif resource == "branch":
        data.customer_branch_id = branch.id
    else:
        data.incoming_id, data.expected_incoming_version = lead.id, lead.version
    with pytest.raises(HTTPException) as exc:
        await create_service_order(db, actor, data)
    assert exc.value.status_code == 404
    assert await count(db, Order) == 0


@pytest.mark.asyncio
async def test_service_order_revoked_actor_cannot_create(db):
    actor, data, membership = await setup(db)
    membership.status = "suspended"
    db.add(membership)
    await db.commit()
    with pytest.raises(HTTPException) as exc:
        await create_service_order(db, actor, data)
    assert exc.value.status_code == 403
    assert await count(db, Order) == 0


@pytest.mark.asyncio
async def test_service_order_outer_receipt_failure_rolls_back_order_and_proposal(db):
    actor, data, _ = await setup(db)
    with pytest.raises(RuntimeError, match="receipt failed"):
        async with command_transaction(db):
            await create_service_order(db, actor, data)
            raise RuntimeError("receipt failed")
    assert await count(db, Order) == await count(db, OrderProposal) == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"workflow_type": "sales_installation"},
        {"workflow_type": "repair", "service_type": "install_only"},
        {"incoming_id": 1},
        {"expected_incoming_version": 1},
        {"incoming_order_id": 1},
        {"expected_incoming_order_revision": 0},
        {
            "incoming_id": 1,
            "expected_incoming_version": 1,
            "incoming_order_id": 2,
            "expected_incoming_order_revision": 0,
        },
        {"customer_id": 0},
        {"tenant_id": 2},
    ],
)
def test_service_order_input_rejects_unsafe_or_inconsistent_creation(changes):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ServiceOrderCreateInput.model_validate(
            {
                "idempotency_key": "service-order-create-test-0001",
                "customer_id": 1,
                "workflow_type": "repair",
                **changes,
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("has_customer", [False, True])
@pytest.mark.parametrize("workflow", ["repair", "maintenance"])
async def test_existing_incoming_order_promotes_same_id_without_replacing_history(db, has_customer, workflow):
    from models.leads_inbox import InboxEvent

    actor, data, _ = await setup(db)
    incoming = Order(
        tenant_id=1,
        storefront_id=1,
        status="new_lead",
        workflow_revision=4,
        customer_id=data.customer_id if has_customer else None,
        responsible_staff_user_id=actor.staff_user_id,
        comment="Original tender request",
        lead_source="email",
        source_fingerprint="original-message",
        title="Source tender",
        technical_meta={
            "incoming_intake": {"original_text": "Verbatim intake"},
            "tender": {"external_id": "test-tender"},
        },
    )
    db.add(incoming)
    await db.flush()
    proposal = OrderProposal(order_id=incoming.id, name="Reviewed draft", status="draft", is_selected=True)
    db.add(proposal)
    await db.flush()
    line = OrderServiceLink(
        order_id=incoming.id,
        proposal_id=proposal.id,
        title="Existing service",
        price=10,
    )
    history = InboxEvent(
        entity_kind="order",
        entity_id=incoming.id,
        order_id=incoming.id,
        tenant_id=1,
        storefront_id=1,
        kind="note",
        actor=actor.username,
        note="Original history",
    )
    db.add_all([line, history])
    await db.commit()
    data = data.model_copy(
        update={
            "incoming_order_id": incoming.id,
            "expected_incoming_order_revision": 4,
            "workflow_type": workflow,
            "request_text": None,
        }
    )
    result = await create_service_order(db, actor, data)
    await db.refresh(incoming)
    await db.refresh(line)
    assert result.order_id == incoming.id and result.proposal_id == proposal.id
    assert result.incoming_order_id == incoming.id and result.incoming_order_revision == 5
    assert incoming.status == "negotiation" and incoming.workflow_type == workflow
    assert incoming.customer_id == data.customer_id
    assert incoming.responsible_staff_user_id == actor.staff_user_id
    assert incoming.comment == "Original tender request"
    assert incoming.lead_source == "email" and incoming.source_fingerprint == "original-message"
    assert incoming.technical_meta["incoming_intake"] == {"original_text": "Verbatim intake"}
    assert incoming.technical_meta["tender"] == {"external_id": "test-tender"}
    assert incoming.installation_date is None and incoming.measurement_date is None
    assert line.title == "Existing service" and line.price == 10
    assert (await db.get(InboxEvent, history.id)).note == "Original history"
    customer = await db.get(Customer, data.customer_id)
    assert customer.name == "Existing repair customer" and customer.phone == ""
    assert await count(db, Customer) == await count(db, Order) == await count(db, OrderProposal) == 1
    assert await count(db, OrderServiceLink) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "revision",
        "customer",
        "branch",
        "status",
        "archived",
        "sent",
        "foreign_storefront",
    ],
)
async def test_existing_incoming_order_rejects_unsafe_promotion_atomically(db, reason):
    from datetime import datetime, timezone
    from models.leads_inbox import InboxTriageState

    actor, data, _ = await setup(db)
    other = Customer(tenant_id=1, name="Another customer", phone="")
    db.add(other)
    await db.flush()
    branch = CustomerBranch(customer_id=data.customer_id, delivery_address="First site")
    db.add(branch)
    await db.flush()
    incoming = Order(
        tenant_id=1,
        storefront_id=1,
        status="new_lead",
        workflow_revision=4,
        customer_id=other.id if reason == "customer" else data.customer_id,
        customer_branch_id=branch.id if reason == "branch" else None,
        comment="Original",
        responsible_staff_user_id=actor.staff_user_id,
    )
    if reason == "status":
        incoming.status = "negotiation"
    if reason == "foreign_storefront":
        db.add(Storefront(id=3, tenant_id=1, slug="other", display_name="Other"))
        await db.flush()
        incoming.storefront_id = 3
    db.add(incoming)
    await db.flush()
    if reason == "sent":
        db.add(OrderProposal(order_id=incoming.id, name="Sent", status="sent", is_selected=True))
    if reason == "archived":
        db.add(
            InboxTriageState(
                entity_kind="order",
                entity_id=incoming.id,
                order_id=incoming.id,
                tenant_id=1,
                storefront_id=1,
                archived_at=datetime.now(timezone.utc),
            )
        )
    if reason == "branch":
        other_branch = CustomerBranch(customer_id=data.customer_id, delivery_address="Second site")
        db.add(other_branch)
        await db.flush()
        data.customer_branch_id = other_branch.id
    await db.commit()
    original_status = incoming.status
    data = data.model_copy(
        update={
            "incoming_order_id": incoming.id,
            "expected_incoming_order_revision": 3 if reason == "revision" else 4,
        }
    )
    with pytest.raises((HTTPException, ValueError)):
        await create_service_order(db, actor, data)
    await db.refresh(incoming)
    assert incoming.status == original_status and incoming.workflow_revision == 4
    assert incoming.comment == "Original"
    assert await count(db, Order) == 1
    assert await count(db, OrderProposal) == (1 if reason == "sent" else 0)


@pytest.mark.asyncio
async def test_existing_incoming_order_creates_empty_proposal_and_preserves_missing_responsible(
    db,
):
    actor, data, _ = await setup(db)
    incoming = Order(tenant_id=1, storefront_id=1, status="new_lead", comment="Intake")
    db.add(incoming)
    await db.commit()
    data = data.model_copy(update={"incoming_order_id": incoming.id, "expected_incoming_order_revision": 0})
    result = await create_service_order(db, actor, data)
    await db.refresh(incoming)
    assert result.order_id == incoming.id and incoming.responsible_staff_user_id is None
    assert result.proposal_status == "draft" and await count(db, OrderProposal) == 1
    assert await count(db, OrderServiceLink) == await count(db, OrderProductLink) == 0
