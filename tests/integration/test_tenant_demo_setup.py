import pytest
from sqlmodel import select

from models import (
    Customer,
    Lead,
    Order,
    OrderProductLink,
    OrderProposal,
    Product,
    Storefront,
    Tenant,
    TenantCatalogGrant,
    TenantDemoFixtureState,
    TenantOffer,
)
from services.tenant_demo_setup_service import (
    TenantDemoSetupBlockedError,
    TenantDemoSetupPlanToken,
    TenantDemoSetupService,
)


async def _seed_target(db):
    tenant = Tenant(
        slug="tenant-demo-test",
        display_name="Tenant demo test",
        kind="independent_seller",
        status="active",
        is_system=False,
    )
    db.add(tenant)
    await db.flush()
    storefront = Storefront(
        tenant_id=tenant.id,
        slug="main",
        display_name="Tenant demo storefront",
        status="active",
        is_default=True,
    )
    db.add(storefront)
    await db.flush()
    grant = TenantCatalogGrant(
        tenant_id=tenant.id,
        storefront_id=storefront.id,
        status="active",
        revision=1,
        created_by_username="test",
        updated_by_username="test",
    )
    products = [
        Product(title="Demo source 1", slug="demo-source-1", price=2500),
        Product(title="Demo source 2", slug="demo-source-2", price=4200),
        Product(
            title="Unpublished source",
            slug="demo-source-hidden",
            price=100,
            is_published=False,
        ),
    ]
    db.add_all([grant, *products])
    await db.flush()
    offers = [
        TenantOffer(
            tenant_id=tenant.id,
            storefront_id=storefront.id,
            product_id=product.id,
            catalog_grant_id=grant.id,
            price=price,
            is_published=True,
            status="active",
            price_source="inherited_master",
            created_by_username="test",
            updated_by_username="test",
        )
        for product, price in zip(products, (2600, 4300, 100), strict=True)
    ]
    db.add_all(offers)
    await db.commit()
    return tenant, storefront, offers, products


@pytest.mark.asyncio
async def test_demo_setup_creates_only_tracked_synthetic_records_and_is_idempotent(db):
    tenant, storefront, offers, products = await _seed_target(db)
    tenant_id = int(tenant.id)
    storefront_id = int(storefront.id)
    product_ids = {int(products[0].id), int(products[1].id)}
    report = await TenantDemoSetupService.plan(
        db,
        tenant_id=tenant.id,
        storefront_id=storefront.id,
    )
    assert report["status"] == "planned"
    assert report["blockers"] == []
    assert report["inventory"] == {
        "customer_ids": [],
        "order_ids": [],
        "lead_ids": [],
    }
    assert [value["offer_id"] for value in report["chosen_offers"]] == [
        offers[0].id,
        offers[1].id,
    ]
    token = TenantDemoSetupPlanToken.issue(plan_digest=report["plan_digest"])

    result = await TenantDemoSetupService.execute(
        db,
        tenant_id=tenant_id,
        storefront_id=storefront_id,
        plan_token=token,
    )
    await db.commit()
    assert result["status"] == "initialized"

    saved_tenant = await db.get(Tenant, tenant_id)
    fixture = await db.get(TenantDemoFixtureState, tenant_id)
    customers = list(
        (
            await db.execute(
                select(Customer)
                .where(Customer.tenant_id == tenant_id)
                .order_by(Customer.id.asc())
            )
        ).scalars().all()
    )
    orders = list(
        (
            await db.execute(
                select(Order)
                .where(Order.tenant_id == tenant_id)
                .order_by(Order.id.asc())
            )
        ).scalars().all()
    )
    proposals = list(
        (
            await db.execute(
                select(OrderProposal)
                .where(OrderProposal.order_id.in_(fixture.order_ids))
                .order_by(OrderProposal.id.asc())
            )
        ).scalars().all()
    )
    lines = list(
        (
            await db.execute(
                select(OrderProductLink)
                .where(OrderProductLink.order_id.in_(fixture.order_ids))
                .order_by(OrderProductLink.id.asc())
            )
        ).scalars().all()
    )
    assert saved_tenant.demo_read_only is True
    assert fixture.customer_ids == [value.id for value in customers]
    assert fixture.order_ids == [value.id for value in orders]
    assert len(customers) == 3
    assert len(orders) == len(proposals) == len(lines) == 2
    assert all(value.name.startswith("[ДЕМО]") for value in customers)
    assert all(value.phone.startswith("Не указан (демо ") for value in customers)
    assert all(value.email.endswith("@example.invalid") for value in customers)
    assert all(value.inn is None for value in customers)
    assert all(value.total_cost == 0 and value.total_payments == 0 for value in orders)
    assert all(value.cost == 0 and value.installation_price == 0 for value in lines)
    assert {value.product_id for value in lines} == product_ids
    assert all(value.is_selected and not value.is_archived for value in proposals)
    assert (
        await db.execute(
            select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.storefront_id == storefront_id,
            )
        )
    ).first() is None

    await db.rollback()
    replay_report = await TenantDemoSetupService.plan(
        db,
        tenant_id=tenant_id,
        storefront_id=storefront_id,
    )
    assert replay_report["status"] == "already_ready"
    assert replay_report["blockers"] == []
    replay_token = TenantDemoSetupPlanToken.issue(
        plan_digest=replay_report["plan_digest"]
    )
    await db.rollback()
    async with db.begin():
        replay = await TenantDemoSetupService.execute(
            db,
            tenant_id=tenant_id,
            storefront_id=storefront_id,
            plan_token=replay_token,
        )
    assert replay["status"] == "already_ready"
    assert replay["customer_ids"] == result["customer_ids"]
    assert replay["order_ids"] == result["order_ids"]


@pytest.mark.asyncio
async def test_demo_setup_blocks_nonempty_or_ineligible_target(db):
    tenant, storefront, _, _ = await _seed_target(db)
    db.add(
        Customer(
            tenant_id=tenant.id,
            name="Existing real customer",
            phone="+375291111111",
        )
    )
    storefront.is_default = False
    await db.commit()

    report = await TenantDemoSetupService.plan(
        db,
        tenant_id=tenant.id,
        storefront_id=storefront.id,
    )
    assert "storefront must be the tenant default" in report["blockers"]
    assert (
        "target CRM is not empty; existing data will not be overwritten"
        in report["blockers"]
    )


@pytest.mark.asyncio
async def test_demo_setup_rejects_offer_change_after_review(db):
    tenant, storefront, offers, _ = await _seed_target(db)
    tenant_id = int(tenant.id)
    storefront_id = int(storefront.id)
    report = await TenantDemoSetupService.plan(
        db,
                    tenant_id=tenant_id,
                    storefront_id=storefront_id,
    )
    token = TenantDemoSetupPlanToken.issue(plan_digest=report["plan_digest"])
    offers[0].price += 50
    await db.commit()

    with pytest.raises(TenantDemoSetupBlockedError, match="State changed"):
        async with db.begin():
            await TenantDemoSetupService.execute(
                db,
                tenant_id=tenant.id,
                storefront_id=storefront.id,
                plan_token=token,
            )
    await db.rollback()
    assert await db.get(TenantDemoFixtureState, tenant_id) is None
    assert (await db.get(Tenant, tenant_id)).demo_read_only is False
