import pytest
from sqlalchemy import delete, func
from sqlmodel import select

from models import Customer, Lead, Order, OrderProductLink, OrderProposal, Product, Storefront, Tenant, TenantOffer
from models.communication import CommunicationDelivery
from models.integration_event import IntegrationOutboxEvent
from services.tenant_training_setup_service import (
    TenantTrainingPlanToken, TenantTrainingSetupBlockedError, TenantTrainingSetupService,
)


async def target(db):
    tenant = Tenant(slug="training-kitlane", display_name="Учебная компания Kitlane")
    db.add(tenant)
    await db.flush()
    storefront = Storefront(tenant_id=tenant.id, slug="main", display_name="Обучение",
                            status="active", is_default=True)
    db.add(storefront)
    await db.flush()
    offers = []
    for index, price in enumerate((2300, 3100)):
        product = Product(title=f"Training equipment {index}", slug=f"training-equipment-{index}", price=price)
        db.add(product)
        await db.flush()
        offer = TenantOffer(tenant_id=tenant.id, storefront_id=storefront.id,
                            product_id=product.id, price=price, status="active", is_published=True,
                            created_by_username="test", updated_by_username="test")
        db.add(offer)
        offers.append(offer)
    await db.commit()
    return dict(tenant_id=int(tenant.id), storefront_id=int(storefront.id), tenant_slug=tenant.slug), offers


async def seed(db, args):
    plan = await TenantTrainingSetupService.plan(db, **args)
    assert plan["blockers"] == []
    result = await TenantTrainingSetupService.execute(db, **args,
        plan_token=TenantTrainingPlanToken.issue(plan_digest=plan["plan_digest"]))
    await db.commit()
    return result


@pytest.mark.asyncio
async def test_additive_editable_fixture_is_private_and_has_no_external_effects(db):
    args, offers = await target(db)
    existing = Customer(tenant_id=args["tenant_id"], name="Existing sandbox client", phone="No phone")
    db.add(existing)
    await db.commit()
    result = await seed(db, args)
    assert result["status"] == "created"
    records = result["records"]
    assert (await db.get(Customer, existing.id)).name == "Existing sandbox client"
    customers = list((await db.execute(select(Customer).where(Customer.id.in_(records["customer_ids"])))).scalars())
    assert len(customers) == 2
    assert {c.type for c in customers} == {"individual", "company"}
    assert all(c.inn is None and c.email.endswith("@example.invalid") for c in customers)
    assert all(c.name.startswith("[ОБУЧЕНИЕ]") for c in customers)
    assert (await db.get(Tenant, args["tenant_id"])).demo_read_only is False
    lead = await db.get(Lead, records["lead_ids"][0])
    assert lead.status == "new" and lead.phone is None and lead.next_followup_date is None
    orders = list((await db.execute(select(Order).where(Order.id.in_(records["order_ids"])))).scalars())
    assert len(orders) == 2
    assert all(o.status == "negotiation" and o.total_amount == offers[0].price and o.total_cost == 0 for o in orders)
    for order in orders:
        proposals = list((await db.execute(select(OrderProposal).where(OrderProposal.order_id == order.id))).scalars())
        assert len(proposals) == 2 and sum(p.is_selected for p in proposals) == 1
        lines = list((await db.execute(select(OrderProductLink).where(OrderProductLink.order_id == order.id))).scalars())
        assert len(lines) == 2 and all(p.price > 0 and p.cost == 0 for p in lines)
    for model in (CommunicationDelivery, IntegrationOutboxEvent):
        assert (await db.execute(select(func.count()).select_from(model))).scalar_one() == 0

    # A recording can edit statuses, names and alternatives. Retry preserves those edits.
    orders[0].status = "execution"
    orders[0].title = "Edited during lesson"
    customers[0].name = "Edited synthetic customer"
    await db.commit()
    retry = await seed(db, args)
    assert retry == {"status": "already_created", "records": records}
    assert (await db.get(Order, orders[0].id)).title == "Edited during lesson"
    assert (await db.execute(select(func.count()).select_from(Customer))).scalar_one() == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("change,expected", [
    ("read_only", "shared read-only demo"), ("slug", "private training-"),
    ("system", "non-system"), ("zero_price", "two current positive-price"),
    ("unpublished", "two current positive-price"),
])
async def test_unsafe_target_or_offers_block_before_writes(db, change, expected):
    args, offers = await target(db)
    tenant = await db.get(Tenant, args["tenant_id"])
    if change == "read_only":
        tenant.demo_read_only = True
    elif change == "slug":
        args["tenant_slug"] = "polotsk"
    elif change == "system":
        tenant.is_system = True
    elif change == "zero_price":
        offers[0].price = 0
    else:
        offers[0].is_published = False
    await db.commit()
    plan = await TenantTrainingSetupService.plan(db, **args)
    assert plan["status"] == "blocked"
    assert any(expected in blocker for blocker in plan["blockers"])
    with pytest.raises(TenantTrainingSetupBlockedError):
        await TenantTrainingSetupService.execute(db, **args,
            plan_token=TenantTrainingPlanToken.issue(plan_digest=plan["plan_digest"]))
    assert (await db.execute(select(func.count()).select_from(Customer))).scalar_one() == 0


@pytest.mark.asyncio
async def test_changed_offer_invalidates_reviewed_plan(db):
    args, offers = await target(db)
    plan = await TenantTrainingSetupService.plan(db, **args)
    offers[0].price += 20
    await db.commit()
    with pytest.raises(TenantTrainingSetupBlockedError, match="State changed"):
        await TenantTrainingSetupService.execute(db, **args,
            plan_token=TenantTrainingPlanToken.issue(plan_digest=plan["plan_digest"]))
    assert (await db.execute(select(func.count()).select_from(Customer))).scalar_one() == 0


@pytest.mark.asyncio
async def test_missing_fixture_line_blocks_without_recreation(db):
    args, _ = await target(db)
    result = await seed(db, args)
    await db.execute(delete(OrderProductLink).where(OrderProductLink.id == result["records"]["line_ids"][0]))
    await db.commit()
    plan = await TenantTrainingSetupService.plan(db, **args)
    assert plan["status"] == "blocked"
    assert any("no automatic repair" in message for message in plan["blockers"])
